from mailwright.pipeline.approval_service import DecisionOutcome
from mailwright.telegram.dispatch import handle_callback


class FakeApproval:
    def __init__(self):
        self.calls = []

    def decide(self, approval_id, action, user_id):
        self.calls.append((approval_id, action, user_id))
        return DecisionOutcome(authorized=True, text="ok", edit_card=True)


def test_handle_callback_dispatches():
    svc = FakeApproval()
    result = handle_callback(svc, "act:approve:7", user_id=111)
    assert result is not None
    action, approval_id, outcome = result
    assert action == "approve" and approval_id == 7
    assert outcome.text == "ok"
    assert svc.calls == [(7, "approve", 111)]


def test_handle_callback_none_on_garbage():
    assert handle_callback(FakeApproval(), "junk", 111) is None
