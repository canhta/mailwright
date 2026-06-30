from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.models import DuplicateCandidate, JiraIssueRef, TicketDraft
from mailwright.jira.ticket_service import TicketService
from mailwright.repositories.thread_ticket_map import ThreadTicketRepo


class FakeJira:
    def __init__(self):
        self.created = []
        self.comments = []
        self.searched = []
        self._n = 0

    def create_issue(self, project_key, draft):
        self._n += 1
        key = f"{project_key}-{self._n}"
        self.created.append((project_key, draft))
        return JiraIssueRef(key=key, url=self.issue_url(key))

    def add_comment(self, key, text):
        self.comments.append((key, text))

    def search_issues(self, jql, max_results=5):
        self.searched.append(jql)
        return [DuplicateCandidate("PROD-1", "Export CSV", "Open", "https://x/browse/PROD-1")]

    def issue_url(self, key):
        return f"https://x/browse/{key}"


def _service(tmp_path, jira):
    conn = get_connection(str(tmp_path / "app.db"))
    init_db(conn)
    return TicketService(jira, ThreadTicketRepo(conn), "PROD"), ThreadTicketRepo(conn)


def _draft():
    return TicketDraft(summary="Add CSV export", description="Please add export")


def test_new_conversation_creates_issue_and_maps(tmp_path):
    jira = FakeJira()
    svc, repo = _service(tmp_path, jira)

    res = svc.create_or_comment("conv-1", "<mid-1>", _draft())

    assert res.created is True
    assert res.commented is False
    assert res.key == "PROD-1"
    assert res.url == "https://x/browse/PROD-1"
    assert len(jira.created) == 1
    assert repo.get("conv-1").ticket_key == "PROD-1"


def test_followup_in_same_conversation_comments_not_creates(tmp_path):
    jira = FakeJira()
    svc, _ = _service(tmp_path, jira)

    svc.create_or_comment("conv-1", "<mid-1>", _draft())
    res = svc.create_or_comment("conv-1", "<mid-2>", _draft())

    assert res.created is False
    assert res.commented is True
    assert res.key == "PROD-1"
    assert len(jira.created) == 1  # no second issue
    assert len(jira.comments) == 1
    assert jira.comments[0][0] == "PROD-1"


def test_find_duplicates_scopes_jql_to_project_and_excludes_done(tmp_path):
    jira = FakeJira()
    svc, _ = _service(tmp_path, jira)

    dups = svc.find_duplicates(_draft())

    assert len(dups) == 1 and dups[0].key == "PROD-1"
    jql = jira.searched[0]
    assert 'project = "PROD"' in jql
    assert "statusCategory != Done" in jql
    assert "Add CSV export" in jql
