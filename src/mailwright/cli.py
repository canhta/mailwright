import sys

import httpx
from openai import OpenAI

from mailwright.brain.classifier import MailClassifier
from mailwright.brain.drafter import TicketDrafter
from mailwright.brain.llm import build_structured_llm
from mailwright.brain.triage import TriageService
from mailwright.config import Settings
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.models import Message
from mailwright.owa.rest_client import OutlookRestClient
from mailwright.owa.session import (
    OwaSession,
    interactive_login,
    playwright_token_extractor,
)
from mailwright.poller.mail_poller import MailPoller
from mailwright.repositories.processed_mails import ProcessedMailRepo


class _TriageRunner:
    def __init__(self, repo, classifier_llm, drafter_llm, threshold):
        self._repo = repo
        self._classifier = MailClassifier(classifier_llm)
        self._drafter = TicketDrafter(drafter_llm)
        self._svc = TriageService(self._classifier, self._drafter, threshold)

    def run(self):
        results = []
        for pm in self._repo.list_by_action("pending"):
            msg = Message(
                id="",
                internet_message_id=pm.message_id,
                conversation_id=pm.conversation_id or "",
                sender=pm.sender or "",
                subject=pm.subject or "",
                received_at=pm.received_at or "",
                body_preview="",
                body=pm.subject or "",
            )
            res = self._svc.triage(msg)
            summary = res.draft.summary if res.draft else "-"
            results.append((pm.message_id, res.action, summary))
        return results


def _build_triage() -> "_TriageRunner":
    settings = Settings()
    conn = get_connection(settings.db_path)
    init_db(conn)
    repo = ProcessedMailRepo(conn)
    # The openai SDK doubles as a generic OpenAI-compatible client; base_url
    # empty -> OpenAI, else DeepSeek/Ollama/etc.
    client_kwargs = {"api_key": settings.llm_api_key or "x"}
    if settings.llm_base_url:
        client_kwargs["base_url"] = settings.llm_base_url
    client = OpenAI(**client_kwargs)
    mode = settings.llm_structured_mode
    return _TriageRunner(
        repo,
        build_structured_llm(client, settings.llm_classify_model, mode),
        build_structured_llm(client, settings.llm_draft_model, mode),
        settings.confidence_threshold,
    )


def _build_poller() -> MailPoller:
    settings = Settings()
    conn = get_connection(settings.db_path)
    init_db(conn)
    repo = ProcessedMailRepo(conn)
    session = OwaSession(lambda: playwright_token_extractor(settings.owa_profile_path))
    client = OutlookRestClient(session.get_token, httpx.Client(timeout=30))
    return MailPoller(client, repo, settings)


def _cmd_login() -> int:
    settings = Settings()
    interactive_login(settings.owa_profile_path)
    print("Login complete; OWA session profile saved.")
    return 0


def _cmd_poll() -> int:
    poller = _build_poller()
    new = poller.poll()
    print(f"Stored {len(new)} new candidate mail(s):")
    for m in new:
        print(f"  - {m.internet_message_id}  {m.subject}")
    return 0


def _cmd_triage() -> int:
    runner = _build_triage()
    for message_id, action, summary in runner.run():
        print(f"  [{action}] {message_id}  {summary}")
    return 0


def _build_agent_app():
    from mailwright.telegram.bot import build_agent

    return build_agent(Settings())


def _run_agent() -> None:
    import asyncio

    from mailwright.telegram.bot import run_agent

    asyncio.run(run_agent(Settings()))


def _cmd_agent() -> int:
    _run_agent()
    return 0


def run(argv: list[str]) -> int:
    if not argv:
        print("usage: mailwright <login|poll|triage|agent>", file=sys.stderr)
        return 2
    cmd = argv[0]
    if cmd == "login":
        return _cmd_login()
    if cmd == "poll":
        return _cmd_poll()
    if cmd == "triage":
        return _cmd_triage()
    if cmd == "agent":
        return _cmd_agent()
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
