import mailwright.cli as cli


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
