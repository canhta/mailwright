import zoneinfo

from mailwright.config import Settings
from mailwright.telegram.bot import build_agent


def _settings(tmp_path, monkeypatch) -> Settings:
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
    return Settings()


def test_build_agent_schedules_daily_jobs_in_configured_timezone(tmp_path, monkeypatch):
    settings = _settings(tmp_path, monkeypatch)

    app = build_agent(settings)

    assert app.bot.defaults.tzinfo == zoneinfo.ZoneInfo(settings.timezone)
