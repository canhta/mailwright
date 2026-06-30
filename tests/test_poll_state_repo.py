from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.repositories.poll_state import PollStateRepo


def _repo(tmp_path, default_interval=180):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return PollStateRepo(conn, default_interval)


def test_defaults_before_anything_is_set(tmp_path):
    repo = _repo(tmp_path, default_interval=180)
    state = repo.get()
    assert state.interval_seconds == 180
    assert state.paused is False
    assert state.last_poll_at is None


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


def test_state_survives_a_fresh_repo_instance_on_same_connection(tmp_path):
    repo = _repo(tmp_path)
    repo.set_interval(900)
    repo.set_paused(True)
    repo.mark_polled(42.0)

    repo2 = PollStateRepo(repo.conn, default_interval_seconds=180)
    state = repo2.get()
    assert state.interval_seconds == 900
    assert state.paused is True
    assert state.last_poll_at == 42.0
