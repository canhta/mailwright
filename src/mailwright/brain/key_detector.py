import re

_KEY_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")


def find_jira_keys(text: str) -> list[str]:
    seen: list[str] = []
    for match in _KEY_RE.findall(text or ""):
        if match not in seen:
            seen.append(match)
    return seen


def mail_references_ticket(subject: str, body: str) -> bool:
    return bool(find_jira_keys(f"{subject}\n{body}"))
