from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.rulebook import RulebookRepo


def _repo(tmp_path):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return RulebookRepo(conn)


def test_list_all_returns_every_status(tmp_path):
    rb = _repo(tmp_path)
    rb.add("manual", "Always ask before creating a P1", status="active")
    rb.add("manual", "Old draft rule", status="proposed")

    all_rules = rb.list_all()

    assert {r.status for r in all_rules} == {"active", "proposed"}
    assert len(all_rules) == 2


def test_update_changes_text_and_status(tmp_path):
    rb = _repo(tmp_path)
    rule_id = rb.add("manual", "Original text", status="active")

    updated = rb.update(rule_id, text="Corrected text", status="retired")

    assert updated is True
    row = next(r for r in rb.list_all() if r.id == rule_id)
    assert row.text == "Corrected text"
    assert row.status == "retired"


def test_update_with_only_status_leaves_text_unchanged(tmp_path):
    rb = _repo(tmp_path)
    rule_id = rb.add("manual", "Keep this text", status="active")

    rb.update(rule_id, status="retired")

    row = next(r for r in rb.list_all() if r.id == rule_id)
    assert row.text == "Keep this text"
    assert row.status == "retired"


def test_update_missing_rule_id_returns_false(tmp_path):
    rb = _repo(tmp_path)

    assert rb.update(999, text="whatever") is False


def test_update_with_no_fields_returns_false(tmp_path):
    rb = _repo(tmp_path)
    rule_id = rb.add("manual", "Text", status="active")

    assert rb.update(rule_id) is False
