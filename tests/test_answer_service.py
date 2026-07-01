from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore
from mailwright.pipeline.answer_service import AnswerService
from mailwright.repositories.episodic import EpisodicRepo
from mailwright.repositories.rulebook import RulebookRepo


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
    ep.add("insight", "Auth bugs from example.com tend to be high priority")
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


class FakeJira:
    def __init__(self, fail_keys=()):
        self.deleted: list[str] = []
        self._fail_keys = set(fail_keys)

    def delete_issue(self, key):
        if key in self._fail_keys:
            raise RuntimeError(f"{key} not found")
        self.deleted.append(key)


def _svc_with_jira(tmp_path, jira=None, llm=None):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep = EpisodicRepo(conn)
    vs = VectorStore(conn)
    svc = AnswerService(
        ep,
        vs,
        FakeEmbedder(),
        llm or FakeToolCallLLM(),
        topk=3,
        jira=jira or FakeJira(),
    )
    return svc, ep, vs


def test_delete_jira_issue_tool_deletes_and_cleans_up(tmp_path):
    jira = FakeJira()
    svc, ep, vs = _svc_with_jira(tmp_path, jira=jira)
    ep.add("insight", "something about SU-1718", ref="SU-1718")
    vec = [1.0, 0.0]
    vs.add("fewshot", "SU-1718 text", vec, ref="SU-1718")

    result = svc._dispatch("delete_jira_issue", {"key": "SU-1718"})

    assert jira.deleted == ["SU-1718"]
    assert result == {"key": "SU-1718", "deleted": True}
    assert ep.search("SU-1718", limit=10) == []


def test_delete_jira_issue_tool_reports_failure_without_raising(tmp_path):
    jira = FakeJira(fail_keys={"SU-9999"})
    svc, _, _ = _svc_with_jira(tmp_path, jira=jira)

    result = svc._dispatch("delete_jira_issue", {"key": "SU-9999"})

    assert result["key"] == "SU-9999"
    assert result["deleted"] is False
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


def test_add_rule_tool_persists_active_rule(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )

    result = svc._dispatch("add_rule", {"rule": "Always write tickets in a human voice."})

    assert result["stored"] is True
    active = rb.list_active()
    assert any(r.text == "Always write tickets in a human voice." for r in active)


def test_add_rule_tool_without_rulebook_configured(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
    )

    result = svc._dispatch("add_rule", {"rule": "Some rule"})

    assert result["stored"] is False
    assert "error" in result


def test_add_rule_tool_rejects_empty_rule(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )

    result = svc._dispatch("add_rule", {"rule": "   "})

    assert result["stored"] is False
    assert "error" in result


def test_store_fact_tool_persists_to_vector_store(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    vs = VectorStore(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        vs,
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
    )

    result = svc._dispatch(
        "store_fact", {"fact": "example.com is the new version of legacy legacyapp.example.com"}
    )

    assert result["stored"] is True
    hits = vs.search("fact", [1.0, 0.0], k=5)
    assert any("example.com" in text for text, _ in hits)


def test_store_fact_tool_rejects_empty_fact(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
    )

    result = svc._dispatch("store_fact", {"fact": "  "})

    assert result["stored"] is False
    assert "error" in result


def test_list_memory_tool_returns_rules_and_facts(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    vs = VectorStore(conn)
    rb = RulebookRepo(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        vs,
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )
    rule_id = rb.add("manual", "Always ask before P1s", status="active")
    fact_id = vs.add("fact", "LegacyApp is maintenance-only", [1.0, 0.0])

    result = svc._dispatch("list_memory", {})

    assert result["rules"] == [{"id": rule_id, "text": "Always ask before P1s", "status": "active"}]
    assert len(result["facts"]) == 1
    assert result["facts"][0]["id"] == fact_id
    assert result["facts"][0]["text"] == "LegacyApp is maintenance-only"
    assert "created_at" in result["facts"][0]


def test_list_memory_tool_without_rulebook_configured(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
    )

    result = svc._dispatch("list_memory", {})

    assert result == {"rules": [], "facts": []}


def test_update_rule_tool_edits_text(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    rule_id = rb.add("manual", "Original rule", status="active")
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )

    result = svc._dispatch("update_rule", {"rule_id": rule_id, "text": "Corrected rule"})

    assert result == {"updated": True, "rule_id": rule_id}
    assert any(r.text == "Corrected rule" for r in rb.list_all())


def test_update_rule_tool_retires_a_rule(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    rule_id = rb.add("manual", "Some rule", status="active")
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )

    result = svc._dispatch("update_rule", {"rule_id": rule_id, "status": "retired"})

    assert result["updated"] is True
    assert not any(r.text == "Some rule" for r in rb.list_active())


def test_update_rule_tool_rejects_invalid_status(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    rule_id = rb.add("manual", "Some rule", status="active")
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )

    result = svc._dispatch("update_rule", {"rule_id": rule_id, "status": "deleted"})

    assert result["updated"] is False
    assert "error" in result


def test_update_rule_tool_without_rulebook_configured(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
    )

    result = svc._dispatch("update_rule", {"rule_id": 1, "text": "x"})

    assert result["updated"] is False
    assert "error" in result


def test_update_rule_tool_requires_a_field(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    rule_id = rb.add("manual", "Some rule", status="active")
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )

    result = svc._dispatch("update_rule", {"rule_id": rule_id})

    assert result["updated"] is False
    assert "error" in result


def test_update_rule_tool_missing_id_reports_failure(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        rulebook_repo=rb,
    )

    result = svc._dispatch("update_rule", {"rule_id": 999, "text": "x"})

    assert result["updated"] is False
    assert "error" in result


def test_memory_write_tools_available_without_jira(tmp_path):
    captured = {}

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            captured["tools"] = tools
            return "reply"

    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        RecordingLLM(),
        topk=3,
    )

    svc.answer("remember that example-app is the new legacyapp")

    names = {t["function"]["name"] for t in captured["tools"]}
    assert "store_fact" in names
    assert "add_rule" in names


def test_fact_stored_via_chat_is_surfaced_in_drafting_context(tmp_path):
    from mailwright.memory.context import MemoryContext
    from mailwright.repositories.style import StyleRepo

    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    vs = VectorStore(conn)
    embedder = FakeEmbedder()
    svc = AnswerService(EpisodicRepo(conn), vs, embedder, FakeToolCallLLM(), topk=3)

    svc._dispatch("store_fact", {"fact": "LegacyApp is maintenance-only, no new features"})

    ctx = MemoryContext(RulebookRepo(conn), StyleRepo(conn), vs, embedder, topk=3)
    block = ctx.build("draft a ticket for a legacyapp bug")

    assert "LegacyApp is maintenance-only" in block


class FakeOwa:
    def __init__(self, fail=False):
        self.sent: list[tuple] = []
        self._fail = fail

    def send_mail(self, to, subject, body, cc=None, bcc=None):
        if self._fail:
            raise RuntimeError("smtp down")
        self.sent.append((to, subject, body, cc, bcc))


def test_send_email_tool_sends_and_logs(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep = EpisodicRepo(conn)
    owa = FakeOwa()
    svc = AnswerService(
        ep,
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        owa=owa,
    )

    result = svc._dispatch(
        "send_email",
        {"to": ["jane@example.com"], "subject": "Hi", "body": "Quick update."},
    )

    assert result["sent"] is True
    assert owa.sent == [(["jane@example.com"], "Hi", "Quick update.", None, None)]
    recent = ep.recent(limit=5)
    assert any("jane@example.com" in e.content for e in recent)


def test_send_email_tool_passes_cc_and_bcc_and_logs_them(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep = EpisodicRepo(conn)
    owa = FakeOwa()
    svc = AnswerService(
        ep,
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        owa=owa,
    )

    result = svc._dispatch(
        "send_email",
        {
            "to": ["jane@example.com"],
            "subject": "Hi",
            "body": "Quick update.",
            "cc": ["manager@example.com"],
            "bcc": ["archive@example.com"],
        },
    )

    assert result["sent"] is True
    assert owa.sent == [
        (
            ["jane@example.com"],
            "Hi",
            "Quick update.",
            ["manager@example.com"],
            ["archive@example.com"],
        )
    ]
    recent = ep.recent(limit=5)
    assert any(
        "manager@example.com" in e.content and "archive@example.com" in e.content for e in recent
    )


def test_send_email_tool_without_owa_configured(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
    )

    result = svc._dispatch(
        "send_email", {"to": ["jane@example.com"], "subject": "Hi", "body": "Body"}
    )

    assert result["sent"] is False
    assert "error" in result


def test_send_email_tool_requires_all_fields(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        owa=FakeOwa(),
    )

    result = svc._dispatch("send_email", {"to": [], "subject": "", "body": ""})

    assert result["sent"] is False
    assert "error" in result


def test_send_email_tool_reports_failure_without_raising(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        FakeToolCallLLM(),
        topk=3,
        owa=FakeOwa(fail=True),
    )

    result = svc._dispatch(
        "send_email", {"to": ["jane@example.com"], "subject": "Hi", "body": "Body"}
    )

    assert result["sent"] is False
    assert "error" in result


def test_send_email_tool_available_without_jira(tmp_path):
    captured = {}

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            captured["tools"] = tools
            return "reply"

    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        RecordingLLM(),
        topk=3,
        owa=FakeOwa(),
    )

    svc.answer("draft an email")

    names = {t["function"]["name"] for t in captured["tools"]}
    assert "send_email" in names


def test_reset_history_clears_conversation_context(tmp_path):
    received_messages: list[list] = []

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            received_messages.append(list(messages))
            return "reply"

    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        RecordingLLM(),
        topk=3,
    )

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

    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    svc = AnswerService(
        EpisodicRepo(conn),
        VectorStore(conn),
        FakeEmbedder(),
        RecordingLLM(),
        topk=3,
    )

    for i in range(5):
        svc.answer(f"question {i}")

    last_messages = received_messages[-1]
    contents = [m.get("content", "") for m in last_messages]
    assert any("question 0" in c for c in contents)
