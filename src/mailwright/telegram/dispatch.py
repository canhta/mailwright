from mailwright.telegram.auth import decode_action


def handle_callback(approval_service, data: str, user_id: int):
    decoded = decode_action(data)
    if decoded is None:
        return None
    action, approval_id = decoded
    outcome = approval_service.decide(approval_id, action, user_id)
    return action, approval_id, outcome
