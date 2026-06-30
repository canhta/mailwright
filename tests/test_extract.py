import base64

from mailwright.ingest.extract import extract_text, image_data_uri
from mailwright.models import AttachmentContent


def _att(ct, data):
    return AttachmentContent(name="f", content_type=ct, data=data)


def test_extract_plain_text():
    assert extract_text(_att("text/plain", b"hello world")) == "hello world"


def test_extract_unsupported_returns_none():
    assert extract_text(_att("application/zip", b"PK..")) is None


def test_pdf_extraction_uses_pypdf(monkeypatch):
    import mailwright.ingest.extract as ex

    monkeypatch.setattr(ex, "_extract_pdf", lambda data: "PDF TEXT")
    assert extract_text(_att("application/pdf", b"%PDF-1.4")) == "PDF TEXT"


def test_image_data_uri():
    data = b"\x89PNG..."
    uri = image_data_uri(_att("image/png", data))
    assert uri == "data:image/png;base64," + base64.b64encode(data).decode()


def test_image_data_uri_none_for_non_image():
    assert image_data_uri(_att("application/pdf", b"x")) is None
