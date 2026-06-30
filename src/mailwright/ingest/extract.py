import base64
import io

from mailwright.models import AttachmentContent

_DOCX_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _extract_pdf(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _extract_docx(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs).strip()


def extract_text(content: AttachmentContent) -> str | None:
    ct = (content.content_type or "").lower()
    if ct.startswith("text/"):
        return content.data.decode("utf-8", errors="replace")
    if ct == "application/pdf":
        return _extract_pdf(content.data)
    if ct == _DOCX_CT:
        return _extract_docx(content.data)
    return None


def image_data_uri(content: AttachmentContent) -> str | None:
    ct = (content.content_type or "").lower()
    if not ct.startswith("image/"):
        return None
    return f"data:{content.content_type};base64,{base64.b64encode(content.data).decode()}"
