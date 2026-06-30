import re

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600}
_DURATION_RE = re.compile(r"^(\d+)([smh]?)$")


def should_poll_now(
    interval_seconds: float, paused: bool, last_poll_at: float | None, now: float
) -> bool:
    if paused:
        return False
    if last_poll_at is None:
        return True
    return now - last_poll_at >= interval_seconds


def parse_duration(text: str) -> int:
    match = _DURATION_RE.match(text.strip())
    if not match:
        raise ValueError(f"Invalid duration: {text!r}. Use e.g. 300, 45s, 5m, 2h.")
    value, unit = match.groups()
    seconds = int(value) * _UNIT_SECONDS.get(unit, 1)
    if seconds <= 0:
        raise ValueError(f"Duration must be positive: {text!r}")
    return seconds


def humanize_seconds(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        minutes, rest = divmod(seconds, 60)
        return f"{minutes}m{rest}s" if rest else f"{minutes}m"
    hours, rest = divmod(seconds, 3600)
    if rest == 0:
        return f"{hours}h"
    minutes, secs = divmod(rest, 60)
    return f"{hours}h{minutes}m{secs}s" if secs else f"{hours}h{minutes}m"
