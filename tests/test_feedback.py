"""Tests for MemoryManager (the LLM-gated replacement for FeedbackRecorder)."""

from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.models import TicketDraft
from mailwright.llm.schemas import MemoryDecision
from mailwright.memory.manager import MemoryManager
from mailwright.memory.vector_store import VectorStore
from mailwright.repositories.episodic import EpisodicRepo


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeStructuredLLM:
    """Always decides to write a fixed insight."""

    def __init__(self, action="write", insight="Test pattern insight"):
        self._action = action
        self._insight = insight

    def parse(self, system, user, schema):
        return MemoryDecision(action=self._action, insight=self._insight)


def _mgr(tmp_path, llm=None):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    vs = VectorStore(conn)
    ep = EpisodicRepo(conn)
    return MemoryManager(ep, vs, FakeEmbedder(), llm or FakeStructuredLLM()), vs, ep


def test_on_outcome_created_stores_fewshot_and_insight(tmp_path):
    mgr, vs, ep = _mgr(tmp_path)
    draft = TicketDraft("Add CSV export", "desc", "Story", "High")
    mgr.on_outcome("created", "From: pm@x.com\nSubject: Need export", draft, "PROD-7")
    assert vs.search("fewshot", [1.0, 0.0], k=1)[0][0].startswith("Email:")
    entries = ep.recent(limit=5)
    assert any("Test pattern insight" in e.content for e in entries)


def test_on_outcome_skip_stores_fewshot_but_no_episodic(tmp_path):
    mgr, vs, ep = _mgr(tmp_path, FakeStructuredLLM(action="skip", insight=""))
    draft = TicketDraft("Add CSV export", "desc", "Story", "High")
    mgr.on_outcome("created", "From: pm@x.com\nSubject: Need export", draft, "PROD-8")
    assert vs.search("fewshot", [1.0, 0.0], k=1)  # fewshot always added on create
    assert ep.recent(limit=5) == []


def test_on_outcome_rejected_no_fewshot(tmp_path):
    mgr, vs, ep = _mgr(tmp_path)
    mgr.on_outcome("rejected", "From: pm@x.com\nSubject: s", None, "rejected by owner")
    assert vs.search("fewshot", [1.0, 0.0], k=1) == []


def test_llm_failure_does_not_crash(tmp_path):
    class BrokenLLM:
        def parse(self, *a, **kw):
            raise RuntimeError("LLM down")

    mgr, vs, ep = _mgr(tmp_path, BrokenLLM())
    draft = TicketDraft("s", "d", "Bug", "High")
    mgr.on_outcome("created", "From: x\nSubject: y", draft, "PROD-1")  # must not raise
