from mailwright.owa.replies import render_status_reply
from mailwright.pipeline.message_service import OutgoingMessage


class StatusReplyService:
    def __init__(
        self,
        owa,
        thread_repo,
        status_targets: list[str],
        jira_base_url: str,
        status_event_repo=None,
    ) -> None:
        self._owa = owa
        self._thread_repo = thread_repo
        self._targets = status_targets
        self._base = jira_base_url.rstrip("/")
        self._status_event_repo = status_event_repo

    def handle(self, event) -> "OutgoingMessage | None":
        if event.status not in self._targets:
            return None
        rec = self._thread_repo.get_by_ticket_key(event.issue_key)
        if rec is None or not rec.owa_message_id:
            return None
        if event.status in rec.statuses_notified:
            return None
        url = f"{self._base}/browse/{event.issue_key}"
        self._owa.reply_all(
            rec.owa_message_id, render_status_reply(event.issue_key, url, event.status)
        )
        self._thread_repo.add_status_notified(rec.conversation_id, event.status)
        if self._status_event_repo:
            self._status_event_repo.add(event.issue_key, event.status)
        return OutgoingMessage(text=f"📦 {event.issue_key} → {event.status} (replied to thread)")
