from mailwright.brain.drafter import DraftOutcome, TicketDrafter
from mailwright.jira.models import TicketDraft
from mailwright.llm.schemas import Draft
from mailwright.models import Message


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def parse(self, system, user, schema, images=None):
        self.calls.append((system, user, schema, images))
        return self.result


def _msg():
    return Message(
        id="1",
        internet_message_id="<m>",
        conversation_id="c",
        sender="pm@x.com",
        subject="Need CSV export",
        received_at="2026-06-30T00:00:00Z",
        body_preview="",
        body="Please add CSV export to billing.",
    )


def test_draft_maps_llm_output_to_ticketdraft():
    out_draft = Draft(
        summary="Add CSV export to billing",
        description="As a user I want CSV export...",
        issue_type="Story",
        priority="High",
        confidence=0.88,
    )
    drafter = TicketDrafter(FakeLLM(out_draft))

    outcome = drafter.draft(_msg())

    assert isinstance(outcome, DraftOutcome)
    assert isinstance(outcome.draft, TicketDraft)
    assert outcome.draft.summary == "Add CSV export to billing"
    assert outcome.draft.issue_type == "Story"
    assert outcome.draft.priority == "High"
    assert outcome.confidence == 0.88
    assert outcome.issue_type_clear is True


def test_draft_includes_attachment_text_and_images():
    out_draft = Draft(
        summary="s", description="d", issue_type="Task", priority="Medium", confidence=0.9
    )
    llm = FakeLLM(out_draft)
    drafter = TicketDrafter(llm)

    drafter.draft(
        _msg(), attachment_texts=["SPEC: must export CSV"], images=["data:image/png;base64,AAA"]
    )

    system, user, schema, images = llm.calls[0]
    assert "SPEC: must export CSV" in user
    assert images == ["data:image/png;base64,AAA"]


def test_draft_flags_unclear_issue_type():
    out_draft = Draft(
        summary="Something",
        description="...",
        issue_type="Unclear",
        priority="Medium",
        confidence=0.5,
    )
    outcome = TicketDrafter(FakeLLM(out_draft)).draft(_msg())
    assert outcome.issue_type_clear is False


def test_draft_memory_context_prepended_to_system():
    out_draft = Draft(
        summary="s", description="d", issue_type="Task", priority="Medium", confidence=0.9
    )
    llm = FakeLLM(out_draft)
    TicketDrafter(llm).draft(_msg(), memory_context="Rule: be terse.")
    system, _, _, _ = llm.calls[0]
    assert "Rule: be terse." in system
