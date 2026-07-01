import logging

from mailwright.config import Settings
from mailwright.models import Message
from mailwright.repositories.processed_mails import ProcessedMail, ProcessedMailRepo

log = logging.getLogger(__name__)


class MailPoller:
    def __init__(
        self, client, repo: ProcessedMailRepo, settings: Settings, runtime_config=None
    ) -> None:
        self._client = client
        self._repo = repo
        self._settings = settings
        self._runtime_config = runtime_config

    def _sender_allowlist(self) -> list[str]:
        if self._runtime_config is not None:
            return list(self._runtime_config.get().sender_allowlist)
        return self._settings.sender_allowlist

    def _is_allowed(self, sender: str) -> bool:
        s = sender.lower()
        for entry in self._sender_allowlist():
            entry = entry.lower()
            if "@" in entry:
                if s == entry:
                    return True
            elif s.endswith("@" + entry):
                return True
        return False

    def poll(self, since: str | None = None) -> list[Message]:
        messages = self._client.list_messages(self._settings.mail_folder, since=since)
        log.info("poll: fetched %d message(s) from %s", len(messages), self._settings.mail_folder)
        new: list[Message] = []
        for m in messages:
            if not self._is_allowed(m.sender):
                log.debug("poll: skip (not allowed) sender=%s subject=%r", m.sender, m.subject)
                continue
            if self._repo.exists(m.internet_message_id):
                log.debug("poll: skip (already seen) mid=%s", m.internet_message_id)
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
            log.info("poll: stored new mail sender=%s subject=%r", m.sender, m.subject)
            new.append(m)
        log.info("poll: %d new candidate(s)", len(new))
        return new
