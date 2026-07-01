# tests/test_runtime_config_repo.py
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.runtime_config import RuntimeConfigRepo


def _repo(tmp_path, default_interval=180, default_senders=None):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return RuntimeConfigRepo(conn, default_interval, default_senders)


def test_defaults_before_anything_is_set(tmp_path):
    repo = _repo(tmp_path, default_interval=180, default_senders=["a@x.com"])
    state = repo.get()
    assert state.interval_seconds == 180
    assert state.paused is False
    assert state.last_poll_at is None
    assert state.reply_all_enabled is True
    assert state.urgent_ping_enabled is True
    assert state.sender_allowlist == ["a@x.com"]


def test_set_interval_persists(tmp_path):
    repo = _repo(tmp_path)
    repo.set_interval(600)
    assert repo.get().interval_seconds == 600


def test_set_paused_persists(tmp_path):
    repo = _repo(tmp_path)
    repo.set_paused(True)
    assert repo.get().paused is True
    repo.set_paused(False)
    assert repo.get().paused is False


def test_mark_polled_persists_and_preserves_other_fields(tmp_path):
    repo = _repo(tmp_path)
    repo.set_interval(600)
    repo.mark_polled(12345.0)
    state = repo.get()
    assert state.last_poll_at == 12345.0
    assert state.interval_seconds == 600  # untouched by mark_polled


def test_set_reply_all_persists_and_preserves_other_fields(tmp_path):
    repo = _repo(tmp_path)
    repo.set_interval(600)
    repo.set_reply_all(False)
    state = repo.get()
    assert state.reply_all_enabled is False
    assert state.interval_seconds == 600


def test_set_urgent_ping_persists(tmp_path):
    repo = _repo(tmp_path)
    repo.set_urgent_ping(False)
    assert repo.get().urgent_ping_enabled is False
    repo.set_urgent_ping(True)
    assert repo.get().urgent_ping_enabled is True


def test_add_sender_appends_normalized_and_dedupes(tmp_path):
    repo = _repo(tmp_path, default_senders=["a@x.com"])
    repo.add_sender("  B@Y.com  ")
    assert repo.get().sender_allowlist == ["a@x.com", "b@y.com"]
    repo.add_sender("a@x.com")  # duplicate, no-op
    assert repo.get().sender_allowlist == ["a@x.com", "b@y.com"]


def test_remove_sender_removes_and_reports_whether_found(tmp_path):
    repo = _repo(tmp_path, default_senders=["a@x.com", "b@y.com"])
    assert repo.remove_sender("A@X.com") is True
    assert repo.get().sender_allowlist == ["b@y.com"]
    assert repo.remove_sender("nobody@z.com") is False
    assert repo.get().sender_allowlist == ["b@y.com"]


def test_state_survives_a_fresh_repo_instance_on_same_connection(tmp_path):
    repo = _repo(tmp_path)
    repo.set_interval(900)
    repo.set_paused(True)
    repo.mark_polled(42.0)
    repo.set_reply_all(False)
    repo.set_urgent_ping(False)
    repo.add_sender("a@x.com")

    repo2 = RuntimeConfigRepo(repo.conn, default_interval_seconds=180)
    state = repo2.get()
    assert state.interval_seconds == 900
    assert state.paused is True
    assert state.last_poll_at == 42.0
    assert state.reply_all_enabled is False
    assert state.urgent_ping_enabled is False
    assert state.sender_allowlist == ["a@x.com"]
