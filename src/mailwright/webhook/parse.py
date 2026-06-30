import hmac
from dataclasses import dataclass


@dataclass
class WebhookEvent:
    issue_key: str
    status: str


def parse_jira_webhook(payload: dict) -> "WebhookEvent | None":
    issue = payload.get("issue")
    if isinstance(issue, str):
        key, status = issue, payload.get("status")
    elif isinstance(issue, dict):
        key = str(issue.get("key") or "")
        status = (issue.get("fields", {}).get("status") or {}).get("name")
    else:
        return None
    if not key or not status:
        return None
    return WebhookEvent(issue_key=key, status=status)


def verify_secret(provided: str, expected: str) -> bool:
    if not expected:
        return False
    return hmac.compare_digest(provided or "", expected)
