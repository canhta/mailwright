from mailwright.jira.models import TicketDraft
from mailwright.llm.schemas import Classification
from mailwright.models import Message
from mailwright.tasks.drafter import DraftOutcome
from mailwright.tasks.triage import (
    AUTO_CREATE,
    IGNORE,
    NEEDS_APPROVAL,
    SKIP_HAS_TICKET,
    TriageService,
)


class FakeClassifier:
    def __init__(self, result):
        self.result = result

    def classify(self, message):
        return self.result


class FakeDrafter:
    def __init__(self, outcome=None):
        self.outcome = outcome
        self.called = False

    def draft(self, message):
        self.called = True
        return self.outcome


def _msg(subject="Need CSV export", body="Please add CSV export."):
    return Message(
        id="1",
        internet_message_id="<m>",
        conversation_id="c",
        sender="pm@x.com",
        subject=subject,
        received_at="t",
        body_preview="",
        body=body,
    )


def _classification(is_request=True, needs_ticket=True, conf=0.9):
    return Classification(
        is_request=is_request,
        needs_ticket=needs_ticket,
        issue_type="Story",
        priority="High",
        confidence=conf,
        reason="r",
        is_urgent=False,
    )


def _outcome(conf, clear=True):
    return DraftOutcome(
        draft=TicketDraft(summary="s", description="d", issue_type="Story", priority="High"),
        confidence=conf,
        issue_type_clear=clear,
    )


def test_skip_when_mail_already_references_ticket():
    svc = TriageService(FakeClassifier(_classification()), FakeDrafter(), 0.8)
    res = svc.triage(_msg(subject="Re: PROD-12 progress"))
    assert res.action == SKIP_HAS_TICKET
    assert res.existing_keys == ["PROD-12"]
    assert res.draft is None


def test_ignore_when_not_a_request():
    svc = TriageService(FakeClassifier(_classification(is_request=False)), FakeDrafter(), 0.8)
    res = svc.triage(_msg())
    assert res.action == IGNORE
    assert res.draft is None


def test_auto_create_when_confident_and_clear():
    drafter = FakeDrafter(_outcome(conf=0.9, clear=True))
    svc = TriageService(FakeClassifier(_classification()), drafter, 0.8)
    res = svc.triage(_msg())
    assert res.action == AUTO_CREATE
    assert res.draft is not None and res.confidence == 0.9
    assert drafter.called is True


def test_needs_approval_when_low_confidence():
    svc = TriageService(FakeClassifier(_classification()), FakeDrafter(_outcome(0.5)), 0.8)
    assert svc.triage(_msg()).action == NEEDS_APPROVAL


def test_needs_approval_when_issue_type_unclear():
    svc = TriageService(
        FakeClassifier(_classification()), FakeDrafter(_outcome(0.95, clear=False)), 0.8
    )
    assert svc.triage(_msg()).action == NEEDS_APPROVAL
