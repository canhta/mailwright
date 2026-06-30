import base64
import json
import time
from collections.abc import Callable

OWA_URL = "https://outlook.office.com/mail/"

# Hosts that serve the OWA web app and emit the bearer token valid for the
# Outlook REST API. Other Microsoft hosts (arc.msn.com, yammer, delve, ...) also
# emit bearer tokens but with the wrong audience, so we must match these only.
# Microsoft is migrating OWA from outlook.office.com to outlook.cloud.microsoft.
_OWA_TOKEN_HOSTS = ("outlook.office.com", "outlook.cloud.microsoft")


class OwaLoginRequired(RuntimeError):
    """Raised when the persistent OWA session is no longer valid and an
    interactive `login` is needed again."""


def jwt_exp(token: str) -> float | None:
    """Best-effort parse of the `exp` claim from a JWT bearer token.

    Accepts an optional 'Bearer ' prefix. Returns None if it can't be parsed.
    """
    raw = token.split()[-1] if token else ""
    parts = raw.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        data = json.loads(base64.urlsafe_b64decode(payload))
        return float(data["exp"])
    except Exception:  # noqa: BLE001 - tolerate any malformed token
        return None


class OwaSession:
    """Provides a bearer token for the Outlook REST API, extracted from an
    authenticated OWA browser session.

    The actual extraction is injected (`extractor`) so the caching/expiry logic
    is unit-testable; production wires `playwright_token_extractor`.
    """

    def __init__(
        self,
        extractor: Callable[[], str],
        clock: Callable[[], float] = time.time,
        skew_seconds: int = 120,
        fallback_ttl_seconds: int = 1800,
    ) -> None:
        self._extractor = extractor
        self._clock = clock
        self._skew = skew_seconds
        self._fallback_ttl = fallback_ttl_seconds
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        if self._token is not None and self._clock() < self._expires_at - self._skew:
            return self._token
        token = self._extractor()
        exp = jwt_exp(token)
        self._token = token
        self._expires_at = exp if exp is not None else self._clock() + self._fallback_ttl
        return token


# --- Playwright glue (thin; verified manually like the spike) ---------------


def _launch_browser(p, channel_preference=("chrome", "msedge", None)):
    """Prefer a real installed browser (Microsoft login blocks bundled Chromium
    more often); fall back to Playwright's Chromium."""
    last: Exception | None = None
    for channel in channel_preference:
        try:
            if channel:
                return p.chromium.launch(headless=True, channel=channel)
            return p.chromium.launch(headless=True)
        except Exception as e:  # noqa: BLE001
            last = e
    raise last  # type: ignore[misc]


def interactive_login(owa_url: str = OWA_URL) -> dict:
    """One-time headful login. Returns the captured storage_state (cookies +
    localStorage) — the portable artifact needed to mint a token headless
    elsewhere, without copying a whole browser profile directory."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        last: Exception | None = None
        browser = None
        for channel in ("chrome", "msedge", None):
            try:
                if channel:
                    browser = p.chromium.launch(headless=False, channel=channel)
                else:
                    browser = p.chromium.launch(headless=False)
                break
            except Exception as e:  # noqa: BLE001
                last = e
        if browser is None:
            raise last  # type: ignore[misc]
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(owa_url, wait_until="domcontentloaded", timeout=120_000)
        input(
            "\n>>> Sign in with your COMPANY account + MFA.\n"
            ">>> When your INBOX is fully loaded, return here and press ENTER...\n"
        )
        state = ctx.storage_state()
        browser.close()
    return dict(state)


def playwright_token_extractor(state: dict, owa_url: str = OWA_URL, settle_ms: int = 12_000) -> str:
    """Load OWA headless with an injected storage_state and capture the bearer
    token OWA uses for its own API calls. Raises OwaLoginRequired if none is
    seen (session expired)."""
    from playwright.sync_api import sync_playwright

    holder: dict[str, str] = {}

    with sync_playwright() as p:
        browser = _launch_browser(p)
        ctx = browser.new_context(storage_state=state)
        page = ctx.new_page()

        def on_request(req) -> None:
            auth = req.headers.get("authorization", "")
            if (
                auth.lower().startswith("bearer")
                and any(h in req.url for h in _OWA_TOKEN_HOSTS)
                and "token" not in holder
            ):
                holder["token"] = auth

        page.on("request", on_request)
        page.goto(owa_url, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(settle_ms)
        landed = page.url
        browser.close()

    if "token" not in holder:
        raise OwaLoginRequired(f"No OWA token captured (landed on {landed}); run `login` again.")
    return holder["token"]
