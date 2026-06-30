from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Outlook Web (OWA) browser-automation session — encrypted storage_state blob
    owa_state_path: str = "data/owa_state.enc"
    # If set, `login` pushes the captured session here (POST /owa/session) instead
    # of writing it locally; the receiving server must share OWA_UPLOAD_SECRET.
    owa_upload_url: str = ""
    owa_upload_secret: str = ""

    # Mail filtering
    mail_folder: str = "Inbox"
    sender_allowlist: Annotated[list[str], NoDecode] = []
    company_domain: str

    # Storage
    db_path: str = "data/app.db"
    fernet_key: str

    # Jira Cloud
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = ""

    # Poller
    poll_interval_seconds: int = 180

    # LLM (OpenAI-compatible: OpenAI, DeepSeek, Ollama, ...)
    llm_api_key: str = ""
    llm_base_url: str = (
        ""  # "" = OpenAI; else e.g. https://api.deepseek.com or http://localhost:11434/v1
    )
    llm_classify_model: str = "gpt-4o-mini"
    llm_draft_model: str = "gpt-4o"
    llm_structured_mode: str = "json_schema"  # or "json_object" (DeepSeek / older Ollama)
    llm_vision_enabled: bool = False
    confidence_threshold: float = 0.8

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_allowlist: Annotated[list[int], NoDecode] = []

    # Jira status webhook
    webhook_secret: str = ""
    webhook_port: int = 8080
    status_targets: Annotated[list[str], NoDecode] = ["In Prod", "Done"]

    # Embeddings (separate OpenAI-compatible endpoint; DeepSeek has no embeddings)
    embed_api_key: str = ""
    embed_base_url: str = ""
    embed_model: str = "text-embedding-3-small"
    memory_topk: int = 4

    # Proactive output
    summary_time: str = "08:00"
    summary_window_hours: int = 24
    nudge_stale_days: int = 3

    @field_validator("status_targets", mode="before")
    @classmethod
    def _split_status_targets(cls, v: object) -> object:
        if isinstance(v, str):
            return [s.strip() for s in v.split(",") if s.strip()]
        return v

    @field_validator("sender_allowlist", mode="before")
    @classmethod
    def _split_allowlist(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip().lower() for item in v.split(",") if item.strip()]
        return v

    @field_validator("telegram_allowlist", mode="before")
    @classmethod
    def _split_allowlist_ids(cls, v: object) -> object:
        if isinstance(v, str):
            ids = []
            for item in v.split(","):
                item = item.strip()
                if item.isdigit():
                    ids.append(int(item))
            return ids
        return v
