from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.memory.vector_store import VectorStore
from mailwright.pipeline.deletion_service import DeletionService
from mailwright.repositories.episodic import EpisodicRepo


class FakeJira:
    def __init__(self, fail_keys=()):
        self.deleted: list[str] = []
        self._fail_keys = set(fail_keys)

    def delete_issue(self, key):
        if key in self._fail_keys:
            raise RuntimeError(f"{key} not found")
        self.deleted.append(key)


def _svc(tmp_path, jira=None):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    ep = EpisodicRepo(conn)
    vs = VectorStore(conn)
    return DeletionService(jira or FakeJira(), ep, vs), ep, vs


def test_delete_removes_jira_issue_and_cleans_up_memory(tmp_path):
    jira = FakeJira()
    svc, ep, vs = _svc(tmp_path, jira=jira)
    ep.add("insight", "something about SU-1718", ref="SU-1718")
    vs.add("fewshot", "SU-1718 text", [1.0, 0.0], ref="SU-1718")

    outcome = svc.delete("SU-1718")

    assert jira.deleted == ["SU-1718"]
    assert outcome.key == "SU-1718"
    assert outcome.deleted is True
    assert outcome.error is None
    assert ep.search("SU-1718", limit=10) == []


def test_delete_normalizes_key_casing_and_whitespace(tmp_path):
    jira = FakeJira()
    svc, _, _ = _svc(tmp_path, jira=jira)

    outcome = svc.delete(" su-1718 ")

    assert jira.deleted == ["SU-1718"]
    assert outcome.key == "SU-1718"


def test_delete_reports_failure_without_raising(tmp_path):
    jira = FakeJira(fail_keys={"SU-9999"})
    svc, _, _ = _svc(tmp_path, jira=jira)

    outcome = svc.delete("SU-9999")

    assert outcome.key == "SU-9999"
    assert outcome.deleted is False
    assert outcome.error is not None
