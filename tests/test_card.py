from mailwright.jira.models import DuplicateCandidate, TicketDraft
from mailwright.telegram.card import render_approval_card


def _draft():
    return TicketDraft(
        summary="Add CSV export", description="Long body " * 50, issue_type="Story", priority="High"
    )


def test_card_text_and_buttons():
    text, buttons = render_approval_card(7, _draft(), 0.72, [])
    assert "Add CSV export" in text
    assert "Story" in text and "High" in text
    assert "0.72" in text
    assert "<b>" in text  # HTML formatting present
    labels = [b[0] for b in buttons]
    data = [b[1] for b in buttons]
    assert labels == ["✅ Approve", "✏️ Edit", "❌ Reject"]
    assert data == ["act:approve:7", "act:edit:7", "act:reject:7"]


def test_card_escapes_html_in_jira_fields():
    draft = TicketDraft(
        summary="AT&T <issue>", description="body & more", issue_type="Bug", priority="High"
    )
    text, _ = render_approval_card(1, draft, 0.8, [])
    assert "AT&amp;T" in text
    assert "&lt;issue&gt;" in text
    assert "<issue>" not in text


def test_card_shows_duplicates():
    dups = [DuplicateCandidate("PROD-1", "Export CSV", "In Progress", "https://x/PROD-1")]
    text, _ = render_approval_card(7, _draft(), 0.9, dups)
    assert "Possible duplicate" in text
    assert "PROD-1" in text and "Export CSV" in text
