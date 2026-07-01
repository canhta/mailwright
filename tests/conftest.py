import pytest

from mailwright.config import Settings


@pytest.fixture(autouse=True)
def _isolate_dotenv(monkeypatch):
    """Prevent the developer's real `.env` from leaking into tests.

    Settings reads `.env` by default; without this, a populated `.env` in the
    repo root would override the defaults that tests assert on.
    """
    monkeypatch.setitem(Settings.model_config, "env_file", None)
