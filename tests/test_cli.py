import mailwright.cli as cli
from mailwright.crypto import generate_key
from mailwright.owa.state_store import read_state_file


def test_run_poll_invokes_poller(monkeypatch, capsys):
    class FakePoller:
        def poll(self, since=None):
            return [type("M", (), {"internet_message_id": "<a>", "subject": "S"})()]

    monkeypatch.setattr(cli, "_build_poller", lambda: FakePoller())

    code = cli.run(["poll"])

    out = capsys.readouterr().out
    assert code == 0
    assert "<a>" in out
    assert "1" in out  # count reported


def test_run_unknown_command_returns_2(capsys):
    assert cli.run(["bogus"]) == 2


def test_run_agent_invokes_build_and_polling(monkeypatch):
    started = {}

    monkeypatch.setattr(cli, "_run_agent", lambda: started.update({"ran": True}))
    assert cli.run(["agent"]) == 0
    assert started["ran"] is True


def test_login_pushes_to_upload_url_when_configured(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("OWA_UPLOAD_URL", "https://vps.example/owa/session")
    monkeypatch.setenv("OWA_UPLOAD_SECRET", "s3cr3t")
    state = {"cookies": [{"name": "ESTSAUTH"}], "origins": []}
    monkeypatch.setattr(cli, "interactive_login", lambda: state)

    posted = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

    def fake_post(url, json=None, headers=None, timeout=None):
        posted.update(url=url, json=json, headers=headers)
        return FakeResponse()

    monkeypatch.setattr(cli.httpx, "post", fake_post)

    code = cli.run(["login"])

    assert code == 0
    assert posted["url"] == "https://vps.example/owa/session"
    assert posted["json"] == state
    assert posted["headers"]["X-Owa-Upload-Secret"] == "s3cr3t"


def test_login_saves_locally_when_no_upload_url(monkeypatch, tmp_path):
    key = generate_key()
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", key)
    state_path = str(tmp_path / "owa_state.enc")
    monkeypatch.setenv("OWA_STATE_PATH", state_path)
    state = {"cookies": [], "origins": []}
    monkeypatch.setattr(cli, "interactive_login", lambda: state)

    code = cli.run(["login"])

    assert code == 0
    assert read_state_file(state_path, key) == state


def test_run_triage_prints_actions(monkeypatch, capsys):
    class FakeTriageRunner:
        def run(self):
            return [
                ("<a>", "auto_create", "Add CSV export"),
                ("<b>", "needs_approval", "Unclear ask"),
            ]

    monkeypatch.setattr(cli, "_build_triage", lambda: FakeTriageRunner())

    code = cli.run(["triage"])

    out = capsys.readouterr().out
    assert code == 0
    assert "auto_create" in out
    assert "Add CSV export" in out
