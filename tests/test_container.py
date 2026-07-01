from mailwright.agent.service import AnswerService
from mailwright.config import Settings
from mailwright.container import build_container
from mailwright.pipeline.approval_service import ApprovalService
from mailwright.pipeline.message_service import PipelineService
from mailwright.poller.mail_poller import MailPoller


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    return Settings()


def test_build_container_wires_the_full_object_graph(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)

    container = build_container(settings, commands=[("status", "Show status")])

    assert container.settings is settings
    assert isinstance(container.poller, MailPoller)
    assert isinstance(container.pipeline, PipelineService)
    assert isinstance(container.approval_service, ApprovalService)
    assert isinstance(container.answer_service, AnswerService)


def test_build_container_passes_commands_into_answer_service_system_prompt(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)

    container = build_container(settings, commands=[("pause", "Pause automatic polling")])

    assert "/pause" in container.answer_service._system
    assert "Pause automatic polling" in container.answer_service._system


def test_build_container_reuses_one_db_connection_across_repos(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)

    container = build_container(settings, commands=[])

    aid = container.approvals.add("ticket", {"draft": {"summary": "s"}})
    assert container.approval_service._repo.get(aid) is not None
