from mailwright.llm.schemas import Classification
from mailwright.models import Message
from mailwright.tasks.classifier import MailClassifier


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def parse(self, system, user, schema):
        self.calls.append((system, user, schema))
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


def test_classify_passes_mail_and_returns_result():
    expected = Classification(
        is_request=True,
        needs_ticket=True,
        issue_type="Story",
        priority="High",
        confidence=0.92,
        reason="explicit feature ask",
        is_urgent=False,
    )
    llm = FakeLLM(expected)

    got = MailClassifier(llm).classify(_msg())

    assert got is expected
    system, user, schema = llm.calls[0]
    assert schema is Classification
    assert "CSV export" in user
    assert "pm@x.com" in user
    assert "english" in system.lower()
