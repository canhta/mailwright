"""One-off SPIKE (not part of the package).

Decide how OWA browser-automation mail access should work, before reworking M1.

  login  — opens a REAL Chrome/Edge window with a persistent profile. You sign in
           with your COMPANY account + MFA. The window stays open until you press
           ENTER in this terminal; then the session is saved.
  probe  — reuses the saved profile headless and checks TWO mechanisms:
           (a) can we intercept the bearer token OWA uses for its own API calls?
           (b) how many message rows are visible in the DOM?

Run:
    uv add playwright
    uv run playwright install chromium      # (only needed if no Chrome/Edge)
    uv run python spikes/owa_probe.py login  # interactive, on your laptop
    uv run python spikes/owa_probe.py probe   # headless, reports findings

Then paste the `probe` output back. The token-interception result is the
reliable signal we care about; the DOM count is approximate.
"""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PROFILE = Path("data/owa_profile")   # persistent browser profile (gitignored)
STATE = Path("data/owa_state.json")  # exported cookies/localStorage
OWA_URL = "https://outlook.office.com/mail/"


def _launch(p, headless: bool):
    """Prefer a real installed browser (Microsoft login blocks bundled Chromium
    more often). Fall back to Playwright's Chromium."""
    PROFILE.mkdir(parents=True, exist_ok=True)
    last = None
    for channel in ("chrome", "msedge", None):
        try:
            kwargs = dict(user_data_dir=str(PROFILE), headless=headless)
            if channel:
                kwargs["channel"] = channel
            ctx = p.chromium.launch_persistent_context(**kwargs)
            print(f"[browser: {channel or 'bundled chromium'}]")
            return ctx
        except Exception as e:  # noqa: BLE001 - spike
            last = e
    raise last


def login() -> None:
    with sync_playwright() as p:
        ctx = _launch(p, headless=False)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(OWA_URL, wait_until="domcontentloaded", timeout=120_000)
        input(
            "\n>>> Sign in with your COMPANY account + MFA.\n"
            ">>> When your INBOX is fully loaded, come back here and press ENTER...\n"
        )
        ctx.storage_state(path=str(STATE))
        print(f">>> Session saved (profile: {PROFILE}, state: {STATE})")
        ctx.close()


def probe() -> None:
    if not PROFILE.exists():
        print(f"No profile at {PROFILE}. Run `login` first.")
        return

    captured: dict[str, str] = {}
    full_token: dict[str, str] = {}  # not printed
    api_calls: list[str] = []
    rest_result: dict[str, object] = {}

    with sync_playwright() as p:
        ctx = _launch(p, headless=True)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        def on_request(req) -> None:
            url = req.url
            auth = req.headers.get("authorization", "")
            is_api = ("outlook.office.com" in url or "graph.microsoft.com" in url) and (
                "messages" in url or "/api/" in url or "service.svc" in url
            )
            if is_api:
                api_calls.append(url.split("?")[0])
                if auth.lower().startswith("bearer") and "token" not in captured:
                    captured["token"] = auth[:25] + "...(redacted)"
                    captured["endpoint"] = url.split("?")[0]
                    full_token["v"] = auth

        page.on("request", on_request)
        page.goto(OWA_URL, wait_until="domcontentloaded", timeout=120_000)
        page.wait_for_timeout(12_000)  # let the SPA make its API calls

        dom_rows = 0
        for sel in ('div[role="option"]', 'div[role="listitem"]', "div[draggable='true']"):
            try:
                dom_rows = max(dom_rows, page.locator(sel).count())
            except Exception:  # noqa: BLE001 - spike
                pass

        # The real test: can WE call the Outlook REST API with the captured token
        # and get the fields our Message model needs?
        if full_token:
            api = (
                "https://outlook.office.com/api/v2.0/me/mailfolders/inbox/messages"
                "?$top=3&$select=Subject,From,ReceivedDateTime,InternetMessageId,ConversationId"
            )
            try:
                resp = ctx.request.get(
                    api,
                    headers={"Authorization": full_token["v"], "Accept": "application/json"},
                )
                rest_result["status"] = resp.status
                if resp.ok:
                    rest_result["messages"] = [
                        {
                            "received": m.get("ReceivedDateTime"),
                            "from": (m.get("From") or {}).get("EmailAddress", {}).get("Address"),
                            "subject": m.get("Subject"),
                            "has_internet_message_id": bool(m.get("InternetMessageId")),
                            "has_conversation_id": bool(m.get("ConversationId")),
                        }
                        for m in resp.json().get("value", [])
                    ]
                else:
                    rest_result["body"] = resp.text()[:400]
            except Exception as e:  # noqa: BLE001 - spike
                rest_result["error"] = repr(e)

        current_url = page.url
        ctx.close()

    print("\n==== PROBE RESULTS ====")
    print("Landed on URL          :", current_url)
    print("Bearer token intercepted:", "YES" if "token" in captured else "NO")
    if "token" in captured:
        print("  sample endpoint       :", captured["endpoint"])
        print("  token (redacted)      :", captured["token"])
    print("Distinct API endpoints  :", len(set(api_calls)))
    for u in sorted(set(api_calls))[:8]:
        print("   -", u)
    print("DOM message-ish rows    :", dom_rows)
    print("\n---- REST API call test (outlook.office.com/api/v2.0) ----")
    if rest_result:
        print("HTTP status            :", rest_result.get("status"))
        if rest_result.get("messages") is not None:
            for m in rest_result["messages"]:
                print("  -", m["received"], "|", m["from"], "|", m["subject"])
                print("     internetMessageId:", m["has_internet_message_id"],
                      " conversationId:", m["has_conversation_id"])
        if rest_result.get("body"):
            print("  error body:", rest_result["body"])
        if rest_result.get("error"):
            print("  exception:", rest_result["error"])
    else:
        print("  (no token captured, skipped)")
    print("\nInterpretation:")
    if rest_result.get("messages") is not None:
        print("  -> CONFIRMED: we can read mail via Outlook REST API with the captured token.")
    elif "token" in captured:
        print("  -> Token captured but REST call failed — see status/body above.")
    elif dom_rows > 0:
        print("  -> No API token captured; DOM automation is the fallback.")
    elif "login" in current_url or "signin" in current_url:
        print("  -> Session not valid headless (redirected to login). Re-run `login`.")
    else:
        print("  -> No signal; share this output so we can adjust selectors/timing.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "login"
    if cmd not in {"login", "probe"}:
        print("usage: python spikes/owa_probe.py <login|probe>")
        raise SystemExit(2)
    login() if cmd == "login" else probe()
