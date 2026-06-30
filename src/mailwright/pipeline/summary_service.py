from datetime import datetime, timedelta

from mailwright.pipeline.service import OutgoingMessage


class SummaryService:
    def __init__(self, processed_repo, approval_repo, status_repo, window_hours: int) -> None:
        self._processed = processed_repo
        self._approvals = approval_repo
        self._status = status_repo
        self._window = window_hours

    def build(self, now: datetime) -> OutgoingMessage:
        since = (now - timedelta(hours=self._window)).strftime("%Y-%m-%d %H:%M:%S")
        created = self._processed.list_by_action_since("created", since)
        pending = self._approvals.list_pending()
        events = self._status.list_since(since)

        lines = [f"🌅 Daily summary — {now.strftime('%Y-%m-%d')}", ""]
        lines.append(f"Tickets created ({len(created)}):")
        lines += [f"  • {m.ticket_key or '?'} — {m.subject or ''}" for m in created] or ["  none"]
        lines.append("")
        lines.append(f"Pending approvals ({len(pending)}):")
        lines += [
            f"  • #{a.id} {a.payload.get('draft', {}).get('summary', '?')}" for a in pending
        ] or ["  none"]
        lines.append("")
        lines.append(f"Status changes ({len(events)}):")
        lines += [f"  • {e.ticket_key} → {e.status}" for e in events] or ["  none"]
        return OutgoingMessage(text="\n".join(lines))
