import base64
import json

import httpx

from mailwright.jira.adf import adf_from_text
from mailwright.jira.models import DuplicateCandidate, JiraIssueRef, TicketDraft


class JiraClient:
    def __init__(self, base_url: str, email: str, api_token: str, http: httpx.Client) -> None:
        self._base = base_url.rstrip("/")
        self._http = http
        token = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._auth = f"Basic {token}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._auth,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _post(self, url: str, payload: dict) -> httpx.Response:
        return self._http.post(url, content=json.dumps(payload), headers=self._headers())

    def issue_url(self, key: str) -> str:
        return f"{self._base}/browse/{key}"

    def create_issue(self, project_key: str, draft: TicketDraft) -> JiraIssueRef:
        fields: dict = {
            "project": {"key": project_key},
            "summary": draft.summary,
            "issuetype": {"name": draft.issue_type},
            "description": adf_from_text(draft.description),
        }
        if draft.priority:
            fields["priority"] = {"name": draft.priority}
        if draft.labels:
            fields["labels"] = draft.labels

        resp = self._post(f"{self._base}/rest/api/3/issue", {"fields": fields})
        resp.raise_for_status()
        key = resp.json()["key"]
        return JiraIssueRef(key=key, url=self.issue_url(key))

    def add_comment(self, key: str, text: str) -> None:
        resp = self._post(
            f"{self._base}/rest/api/3/issue/{key}/comment",
            {"body": adf_from_text(text)},
        )
        resp.raise_for_status()

    def add_attachment(self, key: str, filename: str, data: bytes, content_type: str) -> None:
        resp = self._http.post(
            f"{self._base}/rest/api/3/issue/{key}/attachments",
            files={"file": (filename, data, content_type)},
            headers={
                "Authorization": self._auth,
                "Accept": "application/json",
                "X-Atlassian-Token": "no-check",
            },
        )
        resp.raise_for_status()

    def search_issues(self, jql: str, max_results: int = 5) -> list[DuplicateCandidate]:
        resp = self._post(
            f"{self._base}/rest/api/3/search/jql",
            {"jql": jql, "fields": ["summary", "status"], "maxResults": max_results},
        )
        resp.raise_for_status()
        out: list[DuplicateCandidate] = []
        for item in resp.json().get("issues", []):
            f = item.get("fields", {})
            out.append(
                DuplicateCandidate(
                    key=item["key"],
                    summary=f.get("summary", "") or "",
                    status=(f.get("status") or {}).get("name", "") or "",
                    url=self.issue_url(item["key"]),
                )
            )
        return out
