from mailwright.agent.service import AnswerService
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore
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


def make_service(tmp_path, llm=None, **kwargs):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep = EpisodicRepo(conn)
    vs = VectorStore(conn)
    svc = AnswerService(ep, vs, FakeEmbedder(), llm or FakeToolCallLLM(), topk=3, **kwargs)
    return svc, ep, vs
