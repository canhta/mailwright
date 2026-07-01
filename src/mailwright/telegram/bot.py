import httpx
import uvicorn
from openai import OpenAI
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from mailwright.agent.service import AnswerService
from mailwright.config import Settings
from mailwright.db.connection import get_connection
from mailwright.db.schema import init_db
from mailwright.jira.client import JiraClient
from mailwright.jira.ticket_service import TicketService
from mailwright.llm.client import ToolCallLLM, build_structured_llm
from mailwright.memory.context import MemoryContext
from mailwright.memory.embedder import OpenAIEmbedder
from mailwright.memory.manager import MemoryManager
from mailwright.memory.vector_store import VectorStore
from mailwright.owa.rest_client import OutlookRestClient
from mailwright.owa.session import OwaSession, playwright_token_extractor
from mailwright.owa.state_store import read_state_file, write_state_file
from mailwright.pipeline.approval_service import ApprovalService
from mailwright.pipeline.attachment_loader import AttachmentLoader
from mailwright.pipeline.deletion_service import DeletionService
from mailwright.pipeline.message_service import PipelineService
from mailwright.pipeline.reflection_service import ReflectionService
from mailwright.pipeline.reply_service import Replier
from mailwright.pipeline.status_service import StatusReplyService
from mailwright.pipeline.upload_service import AttachmentUploader
from mailwright.poller.mail_poller import MailPoller
from mailwright.repositories.approvals import ApprovalRepo
from mailwright.repositories.episodic import EpisodicRepo
from mailwright.repositories.poll_state import PollStateRepo
from mailwright.repositories.processed_mails import ProcessedMailRepo
from mailwright.repositories.rulebook import RulebookRepo
from mailwright.repositories.status_events import StatusEventRepo
from mailwright.repositories.style import StyleRepo
from mailwright.repositories.thread_ticket_map import ThreadTicketRepo
from mailwright.tasks.attachment_gate import AttachmentGate
from mailwright.tasks.classifier import MailClassifier
from mailwright.tasks.drafter import TicketDrafter
from mailwright.telegram.auth import is_authorized
from mailwright.telegram.card import render_approval_card
from mailwright.telegram.handlers import (
    COMMANDS,
    HEARTBEAT_SECONDS,
    _nudge_job,
    _on_callback,
    _on_text,
    _poll_job,
    _reflect_job,
    _summary_job,
)
from mailwright.telegram.notifier import TelegramNotifier
from mailwright.webhook.app import build_webhook_app


def build_agent(settings: Settings) -> Application:
    conn = get_connection(settings.db_path)
    init_db(conn)
    processed = ProcessedMailRepo(conn)
    approvals = ApprovalRepo(conn)
    status_events = StatusEventRepo(conn)
    poll_state = PollStateRepo(conn, settings.poll_interval_seconds)

    session = OwaSession(
        lambda: playwright_token_extractor(
            read_state_file(settings.owa_state_path, settings.fernet_key)
        )
    )
    owa = OutlookRestClient(session.get_token, httpx.Client(timeout=30))
    poller = MailPoller(owa, processed, settings)

    llm_kwargs = {"api_key": settings.llm_api_key or "x"}
    if settings.llm_base_url:
        llm_kwargs["base_url"] = settings.llm_base_url
    oa = OpenAI(**llm_kwargs)
    classify_llm = build_structured_llm(
        oa, settings.llm_classify_model, settings.llm_structured_mode
    )
    draft_llm = build_structured_llm(oa, settings.llm_draft_model, settings.llm_structured_mode)
    triage_llm = build_structured_llm(oa, settings.llm_classify_model, settings.llm_structured_mode)
    classifier = MailClassifier(classify_llm)
    drafter = TicketDrafter(draft_llm)
    gate = AttachmentGate(classify_llm)
    loader = AttachmentLoader(owa, gate, settings.llm_vision_enabled)

    jira = JiraClient(
        settings.jira_base_url,
        settings.jira_email,
        settings.jira_api_token,
        httpx.Client(timeout=30),
    )
    thread_repo = ThreadTicketRepo(conn)
    tickets = TicketService(jira, thread_repo, settings.jira_project_key)

    uploader = AttachmentUploader(owa, jira)
    replier = Replier(owa, thread_repo)

    # Memory substrate
    embed_kwargs = {"api_key": settings.embed_api_key or "x"}
    if settings.embed_base_url:
        embed_kwargs["base_url"] = settings.embed_base_url
    embed_client = OpenAI(**embed_kwargs)
    embedder = OpenAIEmbedder(embed_client, settings.embed_model)
    vector_store = VectorStore(conn)
    episodic = EpisodicRepo(conn)
    rulebook = RulebookRepo(conn)
    style = StyleRepo(conn)
    memory_ctx = MemoryContext(rulebook, style, vector_store, embedder, settings.memory_topk)
    memory_mgr = MemoryManager(episodic, vector_store, embedder, classify_llm)
    tool_llm = ToolCallLLM(oa, settings.llm_draft_model)
    answer_svc = AnswerService(
        episodic,
        vector_store,
        embedder,
        tool_llm,
        settings.memory_topk,
        jira=jira,
        project_key=settings.jira_project_key,
        commands=[(c.name, c.description) for c in COMMANDS],
        rulebook_repo=rulebook,
        owa=owa,
    )
    reflection_svc = ReflectionService(episodic, style, rulebook, draft_llm, lookback=50)
    deletion_svc = DeletionService(jira, episodic, vector_store)

    pipeline = PipelineService(
        classifier,
        loader,
        drafter,
        tickets,
        uploader,
        approvals,
        processed,
        settings.confidence_threshold,
        card_renderer=render_approval_card,
        replier=replier,
        feedback=memory_mgr,
        memory_context=memory_ctx,
        triage_llm=triage_llm,
    )
    approval_service = ApprovalService(
        approvals,
        tickets,
        uploader,
        settings.telegram_allowlist,
        auth_check=is_authorized,
        replier=replier,
        feedback=memory_mgr,
    )

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data.update(
        {
            "settings": settings,
            "poller": poller,
            "poll_state": poll_state,
            "pipeline": pipeline,
            "approval_service": approval_service,
            "approvals": approvals,
            "processed": processed,
            "status_events": status_events,
            "owa": owa,
            "jira": jira,
            "episodic": episodic,
            "vector_store": vector_store,
            "thread_repo": thread_repo,
            "answer_service": answer_svc,
            "reflection": reflection_svc,
            "rulebook": rulebook,
            "deletion_service": deletion_svc,
        }
    )
    app.add_handler(CallbackQueryHandler(_on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text))
    for cmd in COMMANDS:
        app.add_handler(CommandHandler(cmd.name, cmd.handler))
    app.job_queue.run_repeating(_poll_job, interval=HEARTBEAT_SECONDS, first=5)
    from datetime import time as dtime

    hh, mm = (int(x) for x in settings.summary_time.split(":"))
    app.job_queue.run_daily(_summary_job, time=dtime(hour=hh, minute=mm))
    app.job_queue.run_daily(_nudge_job, time=dtime(hour=hh, minute=mm))
    app.job_queue.run_daily(_reflect_job, time=dtime(hour=2, minute=0))
    return app


async def run_agent(settings: Settings) -> None:
    app = build_agent(settings)
    status_service = StatusReplyService(
        app.bot_data["owa"],
        app.bot_data["thread_repo"],
        settings.status_targets,
        settings.jira_base_url,
        status_event_repo=app.bot_data["status_events"],
    )
    notifier = TelegramNotifier(app.bot, settings.telegram_chat_id, app.bot_data["approvals"])
    web = build_webhook_app(
        settings.webhook_secret,
        status_service,
        notifier.send,
        settings.owa_upload_secret,
        lambda state: write_state_file(settings.owa_state_path, state, settings.fernet_key),
    )
    config = uvicorn.Config(web, host="0.0.0.0", port=settings.webhook_port, log_level="info")
    server = uvicorn.Server(config)

    async with app:
        await app.start()
        await app.bot.set_my_commands([(c.name, c.description) for c in COMMANDS])
        await app.updater.start_polling()
        await server.serve()
        await app.updater.stop()
        await app.stop()
