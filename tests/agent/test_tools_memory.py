from mailwright.agent.service import AnswerService
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore
from mailwright.repositories.episodic import EpisodicRepo
from mailwright.repositories.rulebook import RulebookRepo
from tests.agent.conftest import FakeEmbedder, FakeToolCallLLM, make_service


def test_search_memory_tool_dispatches_to_episodic(tmp_path):
    svc, ep, _ = make_service(tmp_path)
    ep.add("insight", "Auth bugs from example.com tend to be high priority")
    llm = FakeToolCallLLM(tool_calls=[("search_memory", {"query": "auth bugs"})])
    svc._llm = llm
    svc.answer("tell me about auth bugs")
    assert any(name == "search_memory" for name, _ in llm.dispatched)


def test_get_recent_events_tool_returns_entries(tmp_path):
    svc, ep, _ = make_service(tmp_path)
    ep.add("insight", "Recent pattern A")
    llm = FakeToolCallLLM(tool_calls=[("get_recent_events", {"n": 3})])
    svc._llm = llm
    svc.answer("what happened recently?")
    assert any(name == "get_recent_events" for name, _ in llm.dispatched)


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
    svc, _, _ = make_service(tmp_path)

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
    svc, _, vs = make_service(tmp_path)

    result = svc._dispatch(
        "store_fact", {"fact": "example.com is the new version of legacy legacyapp.example.com"}
    )

    assert result["stored"] is True
    hits = vs.search("fact", [1.0, 0.0], k=5)
    assert any("example.com" in text for text, _ in hits)


def test_store_fact_tool_rejects_empty_fact(tmp_path):
    svc, _, _ = make_service(tmp_path)

    result = svc._dispatch("store_fact", {"fact": "  "})

    assert result["stored"] is False
    assert "error" in result


def test_list_memory_tool_returns_rules_and_facts(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    vs = VectorStore(conn)
    rb = RulebookRepo(conn)
    svc = AnswerService(
        EpisodicRepo(conn), vs, FakeEmbedder(), FakeToolCallLLM(), topk=3, rulebook_repo=rb
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
    svc, _, _ = make_service(tmp_path)

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
    svc, _, _ = make_service(tmp_path)

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


def test_forget_fact_tool_deletes_by_id(tmp_path):
    svc, _, vs = make_service(tmp_path)
    fact_id = vs.add("fact", "Outdated fact", [1.0, 0.0])

    result = svc._dispatch("forget_fact", {"fact_id": fact_id})

    assert result == {"deleted": True, "fact_id": fact_id}
    assert vs.list_by_kind("fact") == []


def test_forget_fact_tool_missing_id_reports_failure(tmp_path):
    svc, _, _ = make_service(tmp_path)

    result = svc._dispatch("forget_fact", {"fact_id": 999})

    assert result["deleted"] is False
    assert "error" in result


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
