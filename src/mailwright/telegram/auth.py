def is_authorized(user_id: int, allowlist: list[int]) -> bool:
    return user_id in allowlist


def encode_action(action: str, approval_id: int) -> str:
    return f"act:{action}:{approval_id}"


def decode_action(data: str) -> tuple[str, int] | None:
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "act":
        return None
    action, raw_id = parts[1], parts[2]
    if not raw_id.isdigit():
        return None
    return action, int(raw_id)
