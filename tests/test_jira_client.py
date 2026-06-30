import base64

import httpx
from mailwright.jira.client import JiraClient
from mailwright.jira.models import TicketDraft

BASE = "https://example.atlassian.net"


def _client(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return JiraClient(BASE, "me@x.com", "tok", http)


def test_create_issue_posts_fields_and_returns_ref():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["auth"] = req.headers.get("authorization")
        seen["body"] = req.read().decode()
        return httpx.Response(201, json={"id": "10001", "key": "PROD-7"})

    client = _client(handler)
    ref = client.create_issue(
        "PROD",
        TicketDraft(
            summary="Add export",
            description="CSV export please",
            issue_type="Story",
            priority="High",
            labels=["product"],
        ),
    )

    assert ref.key == "PROD-7"
    assert ref.url == "https://example.atlassian.net/browse/PROD-7"
    assert seen["url"] == "https://example.atlassian.net/rest/api/3/issue"
    expected_auth = "Basic " + base64.b64encode(b"me@x.com:tok").decode()
    assert seen["auth"] == expected_auth
    assert '"key": "PROD"' in seen["body"]
    assert '"name": "Story"' in seen["body"]
    assert '"name": "High"' in seen["body"]
    assert '"type": "doc"' in seen["body"]  # ADF description


def test_add_comment_posts_adf_body():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = req.read().decode()
        return httpx.Response(201, json={"id": "c1"})

    _client(handler).add_comment("PROD-7", "Follow-up note")

    assert seen["url"] == "https://example.atlassian.net/rest/api/3/issue/PROD-7/comment"
    assert '"type": "doc"' in seen["body"]
    assert "Follow-up note" in seen["body"]


def test_search_issues_uses_jql_endpoint_and_parses_candidates():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = req.read().decode()
        return httpx.Response(
            200,
            json={
                "issues": [
                    {
                        "key": "PROD-1",
                        "fields": {"summary": "Export CSV", "status": {"name": "In Progress"}},
                    },
                ]
            },
        )

    cands = _client(handler).search_issues('project = "PROD" AND text ~ "export"')

    assert seen["url"] == "https://example.atlassian.net/rest/api/3/search/jql"
    assert '"jql"' in seen["body"]
    assert len(cands) == 1
    assert cands[0].key == "PROD-1"
    assert cands[0].summary == "Export CSV"
    assert cands[0].status == "In Progress"
    assert cands[0].url == "https://example.atlassian.net/browse/PROD-1"


def test_add_attachment_posts_multipart_with_token_header():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["token"] = req.headers.get("x-atlassian-token")
        seen["ctype"] = req.headers.get("content-type", "")
        seen["body"] = req.read()
        return httpx.Response(200, json=[{"id": "att1"}])

    _client(handler).add_attachment("PROD-7", "spec.pdf", b"PDFBYTES", "application/pdf")

    assert seen["url"] == "https://example.atlassian.net/rest/api/3/issue/PROD-7/attachments"
    assert seen["token"] == "no-check"
    assert seen["ctype"].startswith("multipart/form-data")
    assert b"spec.pdf" in seen["body"] and b"PDFBYTES" in seen["body"]
