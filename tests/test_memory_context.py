from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.context import MemoryContext
from mailwright.memory.vector_store import VectorStore
from mailwright.repositories.rulebook import RulebookRepo
from mailwright.repositories.style import StyleRepo


class FakeEmbedder:
    def embed(self, texts):
        return [[1.0, 0.0] for _ in texts]


def _ctx(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    rb = RulebookRepo(conn)
    rb.add("hard", "Never auto-reply externally.")
    st = StyleRepo(conn)
    st.set("Terse, bullet points.")
    vs = VectorStore(conn)
    vs.add("fewshot", "EXAMPLE: good ticket", [1.0, 0.0])
    vs.add("fact", "Billing project key is BILL", [1.0, 0.0])
    return MemoryContext(rb, st, vs, FakeEmbedder(), topk=2)


def test_build_includes_all_sections(tmp_path):
    block = _ctx(tmp_path).build("write a billing ticket")
    assert "Never auto-reply externally." in block
    assert "Terse, bullet points." in block
    assert "good ticket" in block
    assert "BILL" in block


def test_build_empty_when_nothing(tmp_path):
    conn = get_connection(str(tmp_path / "e.db"))
    init_db(conn)
    mc = MemoryContext(
        RulebookRepo(conn), StyleRepo(conn), VectorStore(conn), FakeEmbedder(), topk=2
    )
    assert mc.build("anything") == ""
