from mailwright.models import AttachmentContent, AttachmentMeta
from mailwright.pipeline.uploader import AttachmentUploader


class FakeOwa:
    def __init__(self, metas, contents):
        self._metas, self._contents = metas, contents

    def list_attachments(self, mid):
        return self._metas

    def get_attachment(self, mid, aid):
        return self._contents[aid]


class FakeJira:
    def __init__(self):
        self.uploaded = []

    def add_attachment(self, key, name, data, content_type):
        self.uploaded.append((key, name, data, content_type))


def test_no_attachments_is_noop():
    jira = FakeJira()
    n = AttachmentUploader(FakeOwa([], {}), jira).upload_all("m", False, "PROD-1")
    assert n == 0 and jira.uploaded == []


def test_uploads_all_originals():
    metas = [
        AttachmentMeta("a1", "spec.pdf", "application/pdf", 3, False),
        AttachmentMeta("a2", "img.png", "image/png", 4, False),
    ]
    contents = {
        "a1": AttachmentContent("spec.pdf", "application/pdf", b"PDF"),
        "a2": AttachmentContent("img.png", "image/png", b"PNG"),
    }
    jira = FakeJira()
    n = AttachmentUploader(FakeOwa(metas, contents), jira).upload_all("m", True, "PROD-1")
    assert n == 2
    assert ("PROD-1", "spec.pdf", b"PDF", "application/pdf") in jira.uploaded
    assert ("PROD-1", "img.png", b"PNG", "image/png") in jira.uploaded
