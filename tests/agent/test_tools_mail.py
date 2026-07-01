from tests.agent.conftest import make_service


class FakeOwa:
    def __init__(self, fail=False):
        self.sent: list[tuple] = []
        self._fail = fail

    def send_mail(self, to, subject, body, cc=None, bcc=None):
        if self._fail:
            raise RuntimeError("smtp down")
        self.sent.append((to, subject, body, cc, bcc))


def test_send_email_tool_sends_and_logs(tmp_path):
    owa = FakeOwa()
    svc, ep, _ = make_service(tmp_path, owa=owa)

    result = svc._dispatch(
        "send_email",
        {"to": ["jane@example.com"], "subject": "Hi", "body": "Quick update."},
    )

    assert result["sent"] is True
    assert owa.sent == [(["jane@example.com"], "Hi", "Quick update.", None, None)]
    recent = ep.recent(limit=5)
    assert any("jane@example.com" in e.content for e in recent)


def test_send_email_tool_passes_cc_and_bcc_and_logs_them(tmp_path):
    owa = FakeOwa()
    svc, ep, _ = make_service(tmp_path, owa=owa)

    result = svc._dispatch(
        "send_email",
        {
            "to": ["jane@example.com"],
            "subject": "Hi",
            "body": "Quick update.",
            "cc": ["manager@example.com"],
            "bcc": ["archive@example.com"],
        },
    )

    assert result["sent"] is True
    assert owa.sent == [
        (
            ["jane@example.com"],
            "Hi",
            "Quick update.",
            ["manager@example.com"],
            ["archive@example.com"],
        )
    ]
    recent = ep.recent(limit=5)
    assert any(
        "manager@example.com" in e.content and "archive@example.com" in e.content for e in recent
    )


def test_send_email_tool_without_owa_configured(tmp_path):
    svc, _, _ = make_service(tmp_path)

    result = svc._dispatch(
        "send_email", {"to": ["jane@example.com"], "subject": "Hi", "body": "Body"}
    )

    assert result["sent"] is False
    assert "error" in result


def test_send_email_tool_requires_all_fields(tmp_path):
    svc, _, _ = make_service(tmp_path, owa=FakeOwa())

    result = svc._dispatch("send_email", {"to": [], "subject": "", "body": ""})

    assert result["sent"] is False
    assert "error" in result


def test_send_email_tool_reports_failure_without_raising(tmp_path):
    svc, _, _ = make_service(tmp_path, owa=FakeOwa(fail=True))

    result = svc._dispatch(
        "send_email", {"to": ["jane@example.com"], "subject": "Hi", "body": "Body"}
    )

    assert result["sent"] is False
    assert "error" in result


def test_send_email_tool_available_without_jira(tmp_path):
    captured = {}

    class RecordingLLM:
        def run(self, system, messages, tools, dispatch, max_iter=5):
            captured["tools"] = tools
            return "reply"

    svc, _, _ = make_service(tmp_path, RecordingLLM(), owa=FakeOwa())

    svc.answer("draft an email")

    names = {t["function"]["name"] for t in captured["tools"]}
    assert "send_email" in names
