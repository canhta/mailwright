from mailwright.agent.service import AnswerService
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore
from mailwright.repositories.episodic import EpisodicRepo
from tests.agent.conftest import FakeEmbedder, FakeToolCallLLM, make_service


def test_answer_returns_llm_response(tmp_path):
    svc, _, _ = make_service(tmp_path, FakeToolCallLLM(answer="42 issues."))
    assert svc.answer("how many tasks?") == "42 issues."


def test_conversation_history_included_in_messages(tmp_path):
    received_messages: list[list] = []

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            received_messages.append(list(messages))
            return "reply"

    svc, _, _ = make_service(tmp_path, RecordingLLM())
    svc.answer("first question")
    svc.answer("follow-up question")

    # second call should include history (first q + first answer)
    second_messages = received_messages[1]
    contents = [m.get("content", "") for m in second_messages]
    assert any("first question" in c for c in contents)


def test_unknown_tool_returns_error(tmp_path):
    svc, _, _ = make_service(tmp_path)
    result = svc._dispatch("nonexistent_tool", {})
    assert "error" in result


def test_system_prompt_includes_available_commands(tmp_path):
    captured = {}

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            captured["system"] = system
            return "reply"

    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        RecordingLLM(),
        topk=3,
        commands=[("pause", "Pause automatic polling"), ("status", "Show poll status")],
    )

    svc.answer("can you pause polling?")

    assert "/pause" in captured["system"]
    assert "Pause automatic polling" in captured["system"]


def test_memory_management_tools_available_without_jira(tmp_path):
    captured = {}

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            captured["tools"] = tools
            return "reply"

    svc, _, _ = make_service(tmp_path, RecordingLLM())

    svc.answer("what do you remember about legacyapp?")

    names = {t["function"]["name"] for t in captured["tools"]}
    assert {"list_memory", "update_rule", "forget_fact"} <= names


def test_memory_write_tools_available_without_jira(tmp_path):
    captured = {}

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            captured["tools"] = tools
            return "reply"

    svc, _, _ = make_service(tmp_path, RecordingLLM())

    svc.answer("remember that example-app is the new legacyapp")

    names = {t["function"]["name"] for t in captured["tools"]}
    assert "store_fact" in names
    assert "add_rule" in names


def test_reset_history_clears_conversation_context(tmp_path):
    received_messages: list[list] = []

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            received_messages.append(list(messages))
            return "reply"

    svc, _, _ = make_service(tmp_path, RecordingLLM())

    svc.answer("first question")
    svc.reset_history()
    svc.answer("second question")

    last_messages = received_messages[-1]
    contents = [m.get("content", "") for m in last_messages]
    assert not any("first question" in c for c in contents)


def test_history_retains_ten_turns(tmp_path):
    received_messages: list[list] = []

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            received_messages.append(list(messages))
            return "reply"

    svc, _, _ = make_service(tmp_path, RecordingLLM())

    for i in range(5):
        svc.answer(f"question {i}")

    last_messages = received_messages[-1]
    contents = [m.get("content", "") for m in last_messages]
    assert any("question 0" in c for c in contents)
