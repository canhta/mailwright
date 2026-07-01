from datetime import datetime, timedelta

from mailwright.pipeline.interfaces import TextFormatter
from mailwright.pipeline.message_service import OutgoingMessage


class NudgeService:
    def __init__(self, approval_repo, stale_days: int, text_escape: TextFormatter) -> None:
        self._approvals = approval_repo
        self._stale_days = stale_days
        self._escape = text_escape

    def build(self, now: datetime) -> "OutgoingMessage | None":
        cutoff = (now - timedelta(days=self._stale_days)).strftime("%Y-%m-%d %H:%M:%S")
        stale = self._approvals.list_pending_older_than(cutoff)
        if not stale:
            return None
        lines = [f"⏰ {len(stale)} approval(s) waiting more than {self._stale_days} day(s):"]
        lines += [
            f"  • #{a.id} {self._escape(a.payload.get('draft', {}).get('summary', '?'))}"
            for a in stale
        ]
        return OutgoingMessage(text="\n".join(lines))
