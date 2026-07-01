import base64

import httpx

from mailwright.models import AttachmentContent, AttachmentMeta
from mailwright.owa.rest_client import OutlookRestClient

SAMPLE = {
    "value": [
        {
            "Id": "AAMk-id-1",
            "InternetMessageId": "<mid-1@x.com>",
            "ConversationId": "conv-1",
            "Subject": "New feature request",
            "BodyPreview": "Please add export",
            "Body": {"ContentType": "Text", "Content": "Please add CSV export to billing"},
            "ReceivedDateTime": "2026-06-30T01:00:00Z",
            "From": {"EmailAddress": {"Name": "Prod", "Address": "Product@X.com"}},
        }
    ]
}


def test_list_messages_parses_pascalcase_and_lowercases_sender():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=SAMPLE)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OutlookRestClient(lambda: "Bearer tok-abc", http)

    msgs = client.list_messages("Inbox")

    assert len(msgs) == 1
    m = msgs[0]
    assert m.id == "AAMk-id-1"
    assert m.internet_message_id == "<mid-1@x.com>"
    assert m.conversation_id == "conv-1"
    assert m.sender == "product@x.com"  # lowercased
    assert m.subject == "New feature request"
    assert m.body == "Please add CSV export to billing"
    assert captured["auth"] == "Bearer tok-abc"
    assert "/me/mailfolders/inbox/messages" in captured["url"]  # well-known lowercased


def test_list_messages_applies_since_filter():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"value": []})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OutlookRestClient(lambda: "Bearer tok", http)

    client.list_messages("Inbox", since="2026-06-29T00:00:00Z")

    assert "ReceivedDateTime" in captured["url"]
    assert "2026-06-29T00" in captured["url"]


def test_list_messages_custom_folder_kept_as_is():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"value": []})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = OutlookRestClient(lambda: "Bearer tok", http)

    client.list_messages("AAMkCustomFolderId")

    assert "/me/mailfolders/AAMkCustomFolderId/messages" in captured["url"]


def test_list_messages_sets_has_attachments_and_text_body_header():
    seen = {}

    def handler(req):
        seen["prefer"] = req.headers.get("prefer")
        return httpx.Response(200, json={"value": [dict(SAMPLE["value"][0], HasAttachments=True)]})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    msgs = OutlookRestClient(lambda: "Bearer t", http).list_messages("Inbox")
    assert msgs[0].has_attachments is True
    assert 'outlook.body-content-type="text"' in (seen["prefer"] or "")


def test_list_attachments_parses_metadata():
    payload = {
        "value": [
            {
                "Id": "att-1",
                "Name": "spec.pdf",
                "ContentType": "application/pdf",
                "Size": 1234,
                "IsInline": False,
            },
        ]
    }
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    metas = OutlookRestClient(lambda: "Bearer t", http).list_attachments("msg-1")
    assert metas == [AttachmentMeta("att-1", "spec.pdf", "application/pdf", 1234, False)]


def test_get_attachment_decodes_content_bytes():
    raw = b"hello pdf bytes"
    payload = {
        "Id": "att-1",
        "Name": "spec.pdf",
        "ContentType": "application/pdf",
        "ContentBytes": base64.b64encode(raw).decode(),
    }
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    got = OutlookRestClient(lambda: "Bearer t", http).get_attachment("msg-1", "att-1")
    assert isinstance(got, AttachmentContent)
    assert got.data == raw
    assert got.content_type == "application/pdf"


def test_reply_all_posts_comment():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = req.read().decode()
        return httpx.Response(202)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    OutlookRestClient(lambda: "Bearer t", http).reply_all("msg-1", "hello there")
    assert seen["url"].endswith("/me/messages/msg-1/replyall")
    assert "hello there" in seen["body"] and "Comment" in seen["body"]


def test_send_mail_posts_message():
    seen = {}

    def handler(req):
        seen["url"] = str(req.url)
        seen["body"] = req.read().decode()
        return httpx.Response(202)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    OutlookRestClient(lambda: "Bearer t", http).send_mail(
        ["jane@example.com"], "Subject line", "Body text"
    )
    assert seen["url"].endswith("/me/sendmail")
    assert "jane@example.com" in seen["body"]
    assert "Subject line" in seen["body"]
    assert "Body text" in seen["body"]
    assert "CcRecipients" not in seen["body"]
    assert "BccRecipients" not in seen["body"]


def test_send_mail_includes_cc_and_bcc_when_given():
    seen = {}

    def handler(req):
        seen["body"] = req.read().decode()
        return httpx.Response(202)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    OutlookRestClient(lambda: "Bearer t", http).send_mail(
        ["jane@example.com"],
        "Subject line",
        "Body text",
        cc=["cc@example.com"],
        bcc=["bcc@example.com"],
    )
    assert "cc@example.com" in seen["body"] and "CcRecipients" in seen["body"]
    assert "bcc@example.com" in seen["body"] and "BccRecipients" in seen["body"]
