from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore
from mailwright.pipeline.answer_service import AnswerService
from mailwright.repositories.episodic import EpisodicRepo


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


class FakeTextLLM:
    def __init__(self):
        self.last_user = None

    def complete(self, system, user):
        self.last_user = user
        return "Answer based on context."


def test_answer_includes_retrieved_context(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep = EpisodicRepo(conn)
    ep.add("ticket_created", "Created PROD-7 for CSV export", ref="PROD-7")
    vs = VectorStore(conn)
    vs.add("fact", "Billing key is BILL", [1.0, 0.0])
    llm = FakeTextLLM()
    out = AnswerService(ep, vs, FakeEmbedder(), llm, topk=3).answer("what about CSV export?")
    assert out == "Answer based on context."
    assert "PROD-7" in llm.last_user and "BILL" in llm.last_user
