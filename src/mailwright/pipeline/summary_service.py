from datetime import datetime, timedelta

from mailwright.pipeline.interfaces import TextFormatter
from mailwright.pipeline.message_service import OutgoingMessage


class SummaryService:
    def __init__(
        self,
        processed_repo,
        approval_repo,
        status_repo,
        window_hours: int,
        text_escape: TextFormatter,
    ) -> None:
        self._processed = processed_repo
        self._approvals = approval_repo
        self._status = status_repo
        self._window = window_hours
        self._escape = text_escape

    def build(self, now: datetime) -> OutgoingMessage:
        since = (now - timedelta(hours=self._window)).strftime("%Y-%m-%d %H:%M:%S")
        created = self._processed.list_by_action_since("created", since)
        pending = self._approvals.list_pending()
        events = self._status.list_since(since)
        h = self._escape

        lines = [f"🌅 Daily summary {now.strftime('%Y-%m-%d')}", ""]
        lines.append(f"Tickets created ({len(created)}):")
        lines += [f"  • {h(m.ticket_key or '?')}: {h(m.subject or '')}" for m in created] or [
            "  none"
        ]
        lines.append("")
        lines.append(f"Pending approvals ({len(pending)}):")
        lines += [
            f"  • #{a.id} {h(a.payload.get('draft', {}).get('summary', '?'))}" for a in pending
        ] or ["  none"]
        lines.append("")
        lines.append(f"Status changes ({len(events)}):")
        lines += [f"  • {h(e.ticket_key)} → {h(e.status)}" for e in events] or ["  none"]
        return OutgoingMessage(text="\n".join(lines))
