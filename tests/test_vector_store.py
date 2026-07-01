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


def test_list_by_kind_returns_id_text_and_timestamp(tmp_path):
    vs = _store(tmp_path)
    fact_id = vs.add("fact", "example.com replaces legacyapp.example.com", [1.0, 0.0])

    rows = vs.list_by_kind("fact")

    assert len(rows) == 1
    row_id, text, created_at = rows[0]
    assert row_id == fact_id
    assert text == "example.com replaces legacyapp.example.com"
    assert created_at


def test_list_by_kind_ignores_other_kinds(tmp_path):
    vs = _store(tmp_path)
    vs.add("fact", "A fact", [1.0, 0.0])
    vs.add("episodic_summary", "Not a fact", [0.0, 1.0])

    rows = vs.list_by_kind("fact")

    assert len(rows) == 1
    assert rows[0][1] == "A fact"


def test_delete_removes_row_by_id(tmp_path):
    vs = _store(tmp_path)
    fact_id = vs.add("fact", "Stale fact", [1.0, 0.0])

    deleted = vs.delete(fact_id)

    assert deleted is True
    assert vs.list_by_kind("fact") == []


def test_delete_missing_id_returns_false(tmp_path):
    vs = _store(tmp_path)

    assert vs.delete(999) is False
