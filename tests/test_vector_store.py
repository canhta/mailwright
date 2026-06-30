from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore


def _store(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return VectorStore(conn)


def test_search_ranks_by_cosine_within_kind(tmp_path):
    vs = _store(tmp_path)
    vs.add("fact", "apples", [1.0, 0.0])
    vs.add("fact", "oranges", [0.0, 1.0])
    vs.add("style", "ignored", [1.0, 0.0])  # different kind

    out = vs.search("fact", [0.9, 0.1], k=2)
    assert out[0][0] == "apples"  # closest
    assert [t for t, _ in out] == ["apples", "oranges"]
    assert all(isinstance(s, float) for _, s in out)


def test_search_respects_k(tmp_path):
    vs = _store(tmp_path)
    for i in range(5):
        vs.add("fact", f"v{i}", [float(i), 1.0])
    assert len(vs.search("fact", [0.0, 1.0], k=2)) == 2
