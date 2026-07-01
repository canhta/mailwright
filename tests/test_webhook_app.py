from fastapi.testclient import TestClient
from mailwright.pipeline.message_service import OutgoingMessage
from mailwright.webhook.app import build_webhook_app


class FakeStatus:
    def __init__(self, out):
        self.out = out
        self.seen = []

    def handle(self, event):
        self.seen.append(event)
        return self.out


def _client(secret, status, sent, owa_secret="", save_owa_state=None):
    app = build_webhook_app(secret, status, lambda m: sent.append(m), owa_secret, save_owa_state)
    return TestClient(app)


def test_rejects_bad_secret():
    c = _client("s3cr3t", FakeStatus(None), [])
    r = c.post(
        "/jira/webhook",
        json={"issue": "PROD-7", "status": "Done"},
        headers={"X-Webhook-Secret": "wrong"},
    )
    assert r.status_code == 401


def test_accepts_and_notifies():
    sent = []
    c = _client("s3cr3t", FakeStatus(OutgoingMessage(text="📦 PROD-7 → Done")), sent)
    r = c.post(
        "/jira/webhook",
        json={"issue": "PROD-7", "status": "Done"},
        headers={"X-Webhook-Secret": "s3cr3t"},
    )
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert sent and "PROD-7" in sent[0].text


def test_health_ok():
    c = _client("s3cr3t", FakeStatus(None), [])
    r = c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_owa_session_rejects_bad_secret():
    saved = []
    c = _client(
        "s3cr3t", FakeStatus(None), [], owa_secret="owa-s3cr3t", save_owa_state=saved.append
    )
    r = c.post(
        "/owa/session",
        json={"cookies": []},
        headers={"X-Owa-Upload-Secret": "wrong"},
    )
    assert r.status_code == 401
    assert saved == []


def test_owa_session_accepts_and_saves():
    saved = []
    c = _client(
        "s3cr3t", FakeStatus(None), [], owa_secret="owa-s3cr3t", save_owa_state=saved.append
    )
    state = {"cookies": [{"name": "ESTSAUTH"}], "origins": []}
    r = c.post(
        "/owa/session",
        json=state,
        headers={"X-Owa-Upload-Secret": "owa-s3cr3t"},
    )
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert saved == [state]
