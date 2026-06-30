import base64
from collections.abc import Callable

import httpx

from mailwright.models import AttachmentContent, AttachmentMeta, Message

# Well-known mail folder names accepted by the Outlook REST API (lowercase).
_WELL_KNOWN_FOLDERS = {
    "inbox",
    "drafts",
    "sentitems",
    "deleteditems",
    "archive",
    "junkemail",
}


class OutlookRestClient:
    """Reads mail from the Outlook REST API v2.0 using a bearer token captured
    from an authenticated OWA session (see OwaSession)."""

    def __init__(
        self,
        token_provider: Callable[[], str],
        http: httpx.Client,
        base_url: str = "https://outlook.office.com/api/v2.0",
    ) -> None:
        self._token_provider = token_provider
        self._http = http
        self._base_url = base_url.rstrip("/")

    def list_messages(self, folder: str, since: str | None = None, top: int = 50) -> list[Message]:
        # Well-known folders are referenced by lowercase name; custom folders
        # keep their given value (a folder id).
        folder_ref = folder.lower() if folder.lower() in _WELL_KNOWN_FOLDERS else folder
        url = f"{self._base_url}/me/mailfolders/{folder_ref}/messages"
        params: dict[str, object] = {
            "$top": top,
            "$orderby": "ReceivedDateTime desc",
            "$select": (
                "Id,InternetMessageId,ConversationId,Subject,"
                "BodyPreview,Body,ReceivedDateTime,From,HasAttachments"
            ),
        }
        if since:
            params["$filter"] = f"ReceivedDateTime ge {since}"

        resp = self._http.get(
            url,
            params=params,  # type: ignore[arg-type]
            headers={
                "Authorization": self._token_provider(),
                "Accept": "application/json",
                "Prefer": 'outlook.body-content-type="text"',
            },
        )
        resp.raise_for_status()
        return [self._parse(item) for item in resp.json().get("value", [])]

    @staticmethod
    def _parse(item: dict) -> Message:
        sender = (item.get("From") or {}).get("EmailAddress", {}).get("Address", "").lower()
        return Message(
            id=item.get("Id", ""),
            internet_message_id=item.get("InternetMessageId", ""),
            conversation_id=item.get("ConversationId", ""),
            sender=sender,
            subject=item.get("Subject", "") or "",
            received_at=item.get("ReceivedDateTime", ""),
            body_preview=item.get("BodyPreview", "") or "",
            body=(item.get("Body") or {}).get("Content", "") or "",
            has_attachments=bool(item.get("HasAttachments", False)),
        )

    def list_attachments(self, message_id: str) -> list[AttachmentMeta]:
        url = f"{self._base_url}/me/messages/{message_id}/attachments"
        resp = self._http.get(
            url, headers={"Authorization": self._token_provider(), "Accept": "application/json"}
        )
        resp.raise_for_status()
        out = []
        for it in resp.json().get("value", []):
            out.append(
                AttachmentMeta(
                    id=it.get("Id", ""),
                    name=it.get("Name", "") or "",
                    content_type=it.get("ContentType", "") or "",
                    size=int(it.get("Size", 0) or 0),
                    is_inline=bool(it.get("IsInline", False)),
                )
            )
        return out

    def reply_all(self, message_id: str, comment: str) -> None:
        resp = self._http.post(
            f"{self._base_url}/me/messages/{message_id}/replyall",
            json={"Comment": comment},
            headers={
                "Authorization": self._token_provider(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()

    def send_mail(
        self,
        to: list[str],
        subject: str,
        body: str,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> None:
        def _recipients(addrs: list[str]) -> list[dict]:
            return [{"EmailAddress": {"Address": addr}} for addr in addrs]

        message: dict = {
            "Subject": subject,
            "Body": {"ContentType": "Text", "Content": body},
            "ToRecipients": _recipients(to),
        }
        if cc:
            message["CcRecipients"] = _recipients(cc)
        if bcc:
            message["BccRecipients"] = _recipients(bcc)

        resp = self._http.post(
            f"{self._base_url}/me/sendmail",
            json={"Message": message, "SaveToSentItems": "true"},
            headers={
                "Authorization": self._token_provider(),
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        resp.raise_for_status()

    def get_attachment(self, message_id: str, attachment_id: str) -> AttachmentContent:
        url = f"{self._base_url}/me/messages/{message_id}/attachments/{attachment_id}"
        resp = self._http.get(
            url, headers={"Authorization": self._token_provider(), "Accept": "application/json"}
        )
        resp.raise_for_status()
        it = resp.json()
        return AttachmentContent(
            name=it.get("Name", "") or "",
            content_type=it.get("ContentType", "") or "",
            data=base64.b64decode(it.get("ContentBytes", "") or ""),
        )
