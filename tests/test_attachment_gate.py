from mailwright.llm.schemas import ReadDecision
from mailwright.models import AttachmentMeta
from mailwright.tasks.attachment_gate import AttachmentGate


class FakeLLM:
    def __init__(self, result=None):
        self.result = result
        self.called = False

    def parse(self, system, user, schema, images=None):
        self.called = True
        return self.result


def test_no_attachments_skips_llm():
    llm = FakeLLM()
    dec = AttachmentGate(llm).decide("subj", "body", [])
    assert dec.read is False
    assert llm.called is False  # cost-effective: no LLM call


def test_with_attachments_asks_llm():
    decision = ReadDecision(read=True, attachment_ids=["att-1"], reason="body says see attached")
    llm = FakeLLM(decision)
    metas = [AttachmentMeta("att-1", "spec.pdf", "application/pdf", 10, False)]
    dec = AttachmentGate(llm).decide("subj", "see attached spec", metas)
    assert llm.called is True
    assert dec.read is True
    assert dec.attachment_ids == ["att-1"]
