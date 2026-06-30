from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.models import TicketDraft
from mailwright.memory.feedback import FeedbackRecorder
from mailwright.memory.vector_store import VectorStore
from mailwright.repositories.episodic import EpisodicRepo


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _rec(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    vs, ep = VectorStore(conn), EpisodicRepo(conn)
    return FeedbackRecorder(FakeEmbedder(), vs, ep), vs, ep


def test_record_created_adds_fewshot_and_episodic(tmp_path):
    rec, vs, ep = _rec(tmp_path)
    rec.record_created(
        "From pm: please add export", TicketDraft("Add CSV export", "desc"), "PROD-7"
    )
    assert vs.search("fewshot", [1.0, 0.0], k=1)[0][0].startswith("Context:")
    assert ep.search("PROD-7")[0].type == "ticket_created"


def test_record_reject_episodic_only(tmp_path):
    rec, vs, ep = _rec(tmp_path)
    rec.record_reject("From pm: spammy", "not a real request")
    assert ep.search("spammy")[0].type == "reject"
    assert vs.search("fewshot", [1.0, 0.0], k=1) == []
