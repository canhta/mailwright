from mailwright.brain.attachment_loader import AttachmentLoader, LoadedAttachments
from mailwright.llm.schemas import ReadDecision
from mailwright.models import AttachmentContent, AttachmentMeta, Message


def _msg(has=True):
    return Message(
        id="msg-1",
        internet_message_id="<m>",
        conversation_id="c",
        sender="p@x.com",
        subject="s",
        received_at="t",
        body_preview="",
        body="see attached",
        has_attachments=has,
    )


class FakeOwa:
    def __init__(self, metas, contents):
        self._metas = metas
        self._contents = contents
        self.fetched = []

    def list_attachments(self, mid):
        return self._metas

    def get_attachment(self, mid, aid):
        self.fetched.append(aid)
        return self._contents[aid]


class FakeGate:
    def __init__(self, decision):
        self.decision = decision
        self.called = False

    def decide(self, subject, body, attachments):
        self.called = True
        return self.decision


def test_no_attachments_returns_empty_without_gate():
    gate = FakeGate(ReadDecision(read=True, attachment_ids=["x"], reason=""))
    loader = AttachmentLoader(FakeOwa([], {}), gate, vision_enabled=True)
    result = loader.load(_msg(has=False))
    assert result == LoadedAttachments([], [])
    assert gate.called is False


def test_reads_only_chosen_attachments_and_respects_vision_flag():
    metas = [
        AttachmentMeta("a1", "spec.txt", "text/plain", 5, False),
        AttachmentMeta("a2", "shot.png", "image/png", 9, False),
    ]
    contents = {
        "a1": AttachmentContent("spec.txt", "text/plain", b"NEED CSV"),
        "a2": AttachmentContent("shot.png", "image/png", b"PNGDATA"),
    }
    gate = FakeGate(ReadDecision(read=True, attachment_ids=["a1", "a2"], reason="r"))

    res_novis = AttachmentLoader(FakeOwa(metas, contents), gate, vision_enabled=False).load(_msg())
    assert res_novis.texts == ["NEED CSV"]
    assert res_novis.images == []  # vision off

    res_vis = AttachmentLoader(FakeOwa(metas, contents), gate, vision_enabled=True).load(_msg())
    assert res_vis.texts == ["NEED CSV"]
    assert len(res_vis.images) == 1 and res_vis.images[0].startswith("data:image/png;base64,")


def test_decision_not_to_read_returns_empty():
    gate = FakeGate(ReadDecision(read=False, attachment_ids=[], reason="body suffices"))
    metas = [AttachmentMeta("a1", "x.txt", "text/plain", 1, False)]
    loader = AttachmentLoader(FakeOwa(metas, {}), gate, vision_enabled=True)
    assert loader.load(_msg()) == LoadedAttachments([], [])
