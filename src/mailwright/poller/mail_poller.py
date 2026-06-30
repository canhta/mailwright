from mailwright.config import Settings
from mailwright.models import Message
from mailwright.repositories.processed_mails import ProcessedMail, ProcessedMailRepo


class MailPoller:
    def __init__(self, client, repo: ProcessedMailRepo, settings: Settings) -> None:
        self._client = client
        self._repo = repo
        self._settings = settings

    def _is_allowed(self, sender: str) -> bool:
        s = sender.lower()
        for entry in self._settings.sender_allowlist:
            entry = entry.lower()
            if "@" in entry:
                if s == entry:
                    return True
            elif s.endswith("@" + entry):
                return True
        return False

    def poll(self, since: str | None = None) -> list[Message]:
        messages = self._client.list_messages(self._settings.mail_folder, since=since)
        new: list[Message] = []
        for m in messages:
            if not self._is_allowed(m.sender):
                continue
            if self._repo.exists(m.internet_message_id):
                continue
            self._repo.add(
                ProcessedMail(
                    message_id=m.internet_message_id,
                    conversation_id=m.conversation_id,
                    sender=m.sender,
                    subject=m.subject,
                    received_at=m.received_at,
                    classification="candidate",
                    action="pending",
                    body=m.body,
                    has_attachments=m.has_attachments,
                )
            )
            new.append(m)
        return new
