from mailwright.jira.models import DuplicateCandidate, TicketDraft
from mailwright.telegram.auth import encode_action
from mailwright.telegram.formatting import h

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
        f"<b>Summary:</b> {h(draft.summary)}",
        f"<b>Type:</b> {h(draft.issue_type)}  <b>Priority:</b> {h(draft.priority or 'none')}",
        f"<b>Confidence:</b> {confidence:.2f}",
        "",
        h(desc),
    ]
    if duplicates:
        lines.append("")
        lines.append("⚠️ Possible duplicates:")
        for d in duplicates:
            lines.append(f"  • {h(d.key)} [{h(d.status)}] {h(d.summary)}")
    text = "\n".join(lines)
    buttons = [
        ("✅ Approve", encode_action("approve", approval_id)),
        ("✏️ Edit", encode_action("edit", approval_id)),
        ("❌ Reject", encode_action("reject", approval_id)),
    ]
    return text, buttons
