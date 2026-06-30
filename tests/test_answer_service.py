from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore
from mailwright.pipeline.answer_service import AnswerService
from mailwright.repositories.episodic import EpisodicRepo


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeToolCallLLM:
    """Simulates the ReAct loop: optionally dispatches tools, then returns a fixed answer."""

    def __init__(self, answer="Answer from tools.", tool_calls=None):
        self._answer = answer
        self._tool_calls = tool_calls or []
        self.dispatched: list[tuple[str, dict]] = []

    def run(self, system, messages, tools, dispatch, max_iter=5):
        for name, args in self._tool_calls:
            dispatch(name, args)
            self.dispatched.append((name, args))
        return self._answer


def _svc(tmp_path, llm=None):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep = EpisodicRepo(conn)
    vs = VectorStore(conn)
    return AnswerService(ep, vs, FakeEmbedder(), llm or FakeToolCallLLM(), topk=3), ep, vs


def test_answer_returns_llm_response(tmp_path):
    svc, _, _ = _svc(tmp_path, FakeToolCallLLM(answer="42 issues."))
    assert svc.answer("how many tasks?") == "42 issues."


def test_search_memory_tool_dispatches_to_episodic(tmp_path):
    svc, ep, _ = _svc(tmp_path)
    ep.add("insight", "Auth bugs from teacherzone tend to be high priority")
    llm = FakeToolCallLLM(tool_calls=[("search_memory", {"query": "auth bugs"})])
    svc._llm = llm
    svc.answer("tell me about auth bugs")
    assert any(name == "search_memory" for name, _ in llm.dispatched)


def test_get_recent_events_tool_returns_entries(tmp_path):
    svc, ep, _ = _svc(tmp_path)
    ep.add("insight", "Recent pattern A")
    llm = FakeToolCallLLM(tool_calls=[("get_recent_events", {"n": 3})])
    svc._llm = llm
    svc.answer("what happened recently?")
    assert any(name == "get_recent_events" for name, _ in llm.dispatched)


def test_conversation_history_included_in_messages(tmp_path):
    received_messages: list[list] = []

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            received_messages.append(list(messages))
            return "reply"

    svc, _, _ = _svc(tmp_path, RecordingLLM())
    svc.answer("first question")
    svc.answer("follow-up question")

    # second call should include history (first q + first answer)
    second_messages = received_messages[1]
    contents = [m.get("content", "") for m in second_messages]
    assert any("first question" in c for c in contents)


def test_unknown_tool_returns_error(tmp_path):
    svc, _, _ = _svc(tmp_path)
    result = svc._dispatch("nonexistent_tool", {})
    assert "error" in result
