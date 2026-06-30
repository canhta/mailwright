from mailwright.config import Settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("SENDER_ALLOWLIST", "a@x.com, Product@Y.com , y.com")

    s = Settings()

    assert s.company_domain == "example.com"
    assert s.owa_profile_path == "data/owa_profile"  # default
    assert s.mail_folder == "Inbox"  # default
    assert s.db_path == "data/app.db"  # default
    assert s.sender_allowlist == ["a@x.com", "product@y.com", "y.com"]


def test_owa_profile_path_override(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("OWA_PROFILE_PATH", "/custom/profile")

    assert Settings().owa_profile_path == "/custom/profile"


def test_jira_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("JIRA_BASE_URL", "https://example.atlassian.net")
    monkeypatch.setenv("JIRA_EMAIL", "me@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "tok-123")
    monkeypatch.setenv("JIRA_PROJECT_KEY", "PROD")

    s = Settings()

    assert s.jira_base_url == "https://example.atlassian.net"
    assert s.jira_email == "me@example.com"
    assert s.jira_api_token == "tok-123"
    assert s.jira_project_key == "PROD"


def test_jira_settings_default_empty(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    assert Settings().jira_base_url == ""


def test_llm_settings_defaults(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    s = Settings()
    assert s.llm_base_url == ""  # OpenAI default
    assert s.llm_classify_model == "gpt-4o-mini"
    assert s.llm_draft_model == "gpt-4o"
    assert s.llm_structured_mode == "json_schema"
    assert s.confidence_threshold == 0.8
    assert s.llm_api_key == ""


def test_vision_flag_default_false(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "x")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    assert Settings().llm_vision_enabled is False


def test_llm_provider_override_deepseek(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "example.com")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("LLM_CLASSIFY_MODEL", "deepseek-chat")
    monkeypatch.setenv("LLM_STRUCTURED_MODE", "json_object")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.6")
    s = Settings()
    assert s.llm_base_url == "https://api.deepseek.com"
    assert s.llm_classify_model == "deepseek-chat"
    assert s.llm_structured_mode == "json_object"
    assert s.confidence_threshold == 0.6


def test_telegram_settings(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "x")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100999")
    monkeypatch.setenv("TELEGRAM_ALLOWLIST", "111, 222 , bad, 333")
    s = Settings()
    assert s.telegram_bot_token == "123:abc"
    assert s.telegram_chat_id == "-100999"
    assert s.telegram_allowlist == [111, 222, 333]


def test_telegram_allowlist_default_empty(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "x")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    assert Settings().telegram_allowlist == []


def test_status_targets_and_webhook(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "x")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setenv("STATUS_TARGETS", "In Prod, Done , Released")
    s = Settings()
    assert s.webhook_secret == "s3cr3t"
    assert s.status_targets == ["In Prod", "Done", "Released"]
    assert s.webhook_port == 8080


def test_summary_nudge_config(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "x")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("SUMMARY_TIME", "07:30")
    monkeypatch.setenv("NUDGE_STALE_DAYS", "5")
    s = Settings()
    assert s.summary_time == "07:30"
    assert s.summary_window_hours == 24
    assert s.nudge_stale_days == 5


def test_embed_config(monkeypatch):
    monkeypatch.setenv("COMPANY_DOMAIN", "x")
    monkeypatch.setenv("FERNET_KEY", "k" * 44)
    monkeypatch.setenv("EMBED_MODEL", "nomic-embed-text")
    monkeypatch.setenv("EMBED_BASE_URL", "http://localhost:11434/v1")
    s = Settings()
    assert s.embed_model == "nomic-embed-text"
    assert s.embed_base_url == "http://localhost:11434/v1"
    assert s.memory_topk == 4
