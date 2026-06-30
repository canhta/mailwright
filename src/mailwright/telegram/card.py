from mailwright.jira.models import DuplicateCandidate, TicketDraft
from mailwright.telegram.auth import encode_action

_MAX_DESC = 600


def render_approval_card(
    approval_id: int,
    draft: TicketDraft,
    confidence: float,
    duplicates: list[DuplicateCandidate],
) -> tuple[str, list[tuple[str, str]]]:
    desc = draft.description
    if len(desc) > _MAX_DESC:
        desc = desc[:_MAX_DESC] + "…"
    lines = [
        "🆕 New ticket proposal",
        f"Summary: {draft.summary}",
        f"Type: {draft.issue_type}   Priority: {draft.priority or '—'}",
        f"Confidence: {confidence:.2f}",
        "",
        desc,
    ]
    if duplicates:
        lines.append("")
        lines.append("⚠️ Possible duplicate(s):")
        for d in duplicates:
            lines.append(f"  • {d.key} [{d.status}] {d.summary}")
    text = "\n".join(lines)
    buttons = [
        ("✅ Approve", encode_action("approve", approval_id)),
        ("✏️ Edit", encode_action("edit", approval_id)),
        ("❌ Reject", encode_action("reject", approval_id)),
    ]
    return text, buttons
