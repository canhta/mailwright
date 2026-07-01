import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import uvicorn
from openai import OpenAI
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from mailwright.brain.attachment_gate import AttachmentGate
from mailwright.brain.attachment_loader import AttachmentLoader
from mailwright.brain.classifier import MailClassifier
from mailwright.brain.drafter import TicketDrafter
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
from mailwright.owa.session import OwaLoginRequired, OwaSession, playwright_token_extractor
from mailwright.owa.state_store import read_state_file, write_state_file
from mailwright.pipeline.answer_service import AnswerService
from mailwright.pipeline.approval_service import ApprovalService
from mailwright.pipeline.nudge_service import NudgeService
from mailwright.pipeline.reflection_service import ReflectionService
from mailwright.pipeline.replier import Replier
from mailwright.pipeline.service import PipelineService
from mailwright.pipeline.status_service import StatusReplyService
from mailwright.pipeline.summary_service import SummaryService
from mailwright.pipeline.uploader import AttachmentUploader
from mailwright.poller.mail_poller import MailPoller
from mailwright.poller.scheduling import humanize_seconds, parse_duration, should_poll_now
from mailwright.repositories.approvals import ApprovalRepo
from mailwright.repositories.episodic import EpisodicRepo
from mailwright.repositories.poll_state import PollStateRepo
from mailwright.repositories.processed_mails import ProcessedMailRepo
from mailwright.repositories.rulebook import RulebookRepo
from mailwright.repositories.status_events import StatusEventRepo
from mailwright.repositories.style import StyleRepo
from mailwright.repositories.thread_ticket_map import ThreadTicketRepo
from mailwright.telegram.dispatch import handle_callback
from mailwright.telegram.formatting import h, md_to_html
from mailwright.telegram.notifier import TelegramNotifier
from mailwright.webhook.app import build_webhook_app

log = logging.getLogger(__name__)

# How often the scheduled job wakes up to *check* whether a poll is due, per
# the persisted (and runtime-adjustable) poll_state interval. Not itself
# user-configurable — /interval below this has no effect.
_HEARTBEAT_SECONDS = 30


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
        commands=[(c.name, c.description) for c in _COMMANDS],
        rulebook_repo=rulebook,
        owa=owa,
    )
    reflection_svc = ReflectionService(episodic, style, rulebook, draft_llm, lookback=50)

    pipeline = PipelineService(
        classifier,
        loader,
        drafter,
        tickets,
        uploader,
        approvals,
        processed,
        settings.confidence_threshold,
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
        }
    )
    app.add_handler(CallbackQueryHandler(_on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text))
    for cmd in _COMMANDS:
        app.add_handler(CommandHandler(cmd.name, cmd.handler))
    app.job_queue.run_repeating(_poll_job, interval=_HEARTBEAT_SECONDS, first=5)
    from datetime import time as dtime

    hh, mm = (int(x) for x in settings.summary_time.split(":"))
    app.job_queue.run_daily(_summary_job, time=dtime(hour=hh, minute=mm))
    app.job_queue.run_daily(_nudge_job, time=dtime(hour=hh, minute=mm))
    app.job_queue.run_daily(_reflect_job, time=dtime(hour=2, minute=0))
    return app


async def _summary_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import datetime

    s = context.bot_data["settings"]
    svc = SummaryService(
        context.bot_data["processed"],
        context.bot_data["approvals"],
        context.bot_data["status_events"],
        s.summary_window_hours,
    )
    await _notifier(context).send(svc.build(datetime.now()))


async def _nudge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import datetime

    s = context.bot_data["settings"]
    msg = NudgeService(context.bot_data["approvals"], s.nudge_stale_days).build(datetime.now())
    if msg is not None:
        await _notifier(context).send(msg)


def _notifier(context) -> TelegramNotifier:
    s = context.bot_data["settings"]
    return TelegramNotifier(context.bot, s.telegram_chat_id, context.bot_data["approvals"])


def _poll_failure_text(exc: Exception) -> str:
    if isinstance(exc, OwaLoginRequired):
        return (
            "🔒 OWA session expired. Run <code>mailwright login</code> on your "
            "laptop to refresh it — it'll push the new session automatically."
        )
    return f"⚠️ Poll failed: {h(exc)}"


async def _run_poll_once(context: ContextTypes.DEFAULT_TYPE) -> None:
    poll_state = context.bot_data["poll_state"]
    pipeline = context.bot_data["pipeline"]
    poller = context.bot_data["poller"]
    notifier = _notifier(context)
    poll_state.mark_polled(time.time())
    log.info("poll_job: starting")
    try:
        new = await asyncio.get_event_loop().run_in_executor(None, poller.poll)
    except Exception as exc:
        log.exception("poll_job: poll failed — %s", exc)
        await context.bot.send_message(
            context.bot_data["settings"].telegram_chat_id,
            _poll_failure_text(exc),
            parse_mode=ParseMode.HTML,
        )
        return
    log.info("poll_job: %d new message(s) to process", len(new))
    for message in new:
        for effect in pipeline.process_message(message):
            await notifier.send(effect)
    log.info("poll_job: done")


async def _poll_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.bot_data["poll_state"].get()
    if not should_poll_now(state.interval_seconds, state.paused, state.last_poll_at, time.time()):
        return
    await _run_poll_once(context)


async def _on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    result = handle_callback(context.bot_data["approval_service"], query.data, query.from_user.id)
    if result is None:
        await query.answer()
        return
    action, approval_id, outcome = result
    if not outcome.authorized:
        await query.answer(outcome.text, show_alert=True)
        return
    await query.answer()
    if outcome.edit_card:
        await query.edit_message_text(outcome.text, parse_mode=ParseMode.HTML)
    if action == "edit":
        context.user_data["awaiting_edit_id"] = approval_id


async def _on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    approval_id = context.user_data.pop("awaiting_edit_id", None)
    if approval_id is not None:
        outcome = context.bot_data["approval_service"].apply_edit(
            approval_id, update.message.text, update.effective_user.id
        )
        await update.message.reply_text(outcome.text, parse_mode=ParseMode.HTML)
        return

    chat_id = update.effective_chat.id

    # Fire immediately so the indicator appears before the executor blocks.
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    async def _keep_typing() -> None:
        while True:
            await asyncio.sleep(4)
            await context.bot.send_chat_action(chat_id, ChatAction.TYPING)

    typing_task = asyncio.create_task(_keep_typing())
    try:
        answer = await asyncio.get_running_loop().run_in_executor(
            None, context.bot_data["answer_service"].answer, update.message.text
        )
    finally:
        typing_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await typing_task

    await update.message.reply_text(md_to_html(answer), parse_mode=ParseMode.HTML)


async def _on_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    rb = context.bot_data["rulebook"]
    if args and args[0] == "approve" and len(args) > 1 and args[1].isdigit():
        rb.activate(int(args[1]))
        await update.message.reply_text(f"Rule {args[1]} activated.", parse_mode=ParseMode.HTML)
        return
    active_text = rb.render()
    active_str = h(active_text) if active_text else "(none)"
    proposed = rb.list_proposed()
    proposed_str = "\n".join(f"  #{r.id} {h(r.text)}" for r in proposed) if proposed else "  (none)"
    await update.message.reply_text(
        f"Active rules:\n{active_str}\n\nProposed (use /rules approve ID):\n{proposed_str}",
        parse_mode=ParseMode.HTML,
    )


async def _on_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keys = context.args
    if not keys:
        await update.message.reply_text("Usage: /delete SU-123 SU-456", parse_mode=ParseMode.HTML)
        return
    jira_client = context.bot_data["jira"]
    episodic = context.bot_data["episodic"]
    vector_store = context.bot_data["vector_store"]
    lines = []
    for key in keys:
        key = key.upper().strip()
        try:
            jira_client.delete_issue(key)
            ep_removed = episodic.delete_by_ref(key)
            vs_removed = vector_store.delete_by_ref(key)
            log.info("delete: removed %s (episodic=%d, vectors=%d)", key, ep_removed, vs_removed)
            lines.append(f"🗑 Deleted {h(key)}")
        except Exception as exc:
            log.warning("delete: failed to remove %s: %s", key, exc)
            lines.append(f"❌ {h(key)}: {h(exc)}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def _on_poll(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Polling now...", parse_mode=ParseMode.HTML)
    await _run_poll_once(context)
    await update.message.reply_text("Done.", parse_mode=ParseMode.HTML)


async def _on_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /interval 5m (also accepts e.g. 300, 45s, 2h)", parse_mode=ParseMode.HTML
        )
        return
    try:
        seconds = parse_duration(args[0])
    except ValueError as exc:
        await update.message.reply_text(h(exc), parse_mode=ParseMode.HTML)
        return
    if seconds < _HEARTBEAT_SECONDS:
        await update.message.reply_text(
            f"Minimum interval is {_HEARTBEAT_SECONDS}s.", parse_mode=ParseMode.HTML
        )
        return
    context.bot_data["poll_state"].set_interval(seconds)
    await update.message.reply_text(
        f"Poll interval set to {humanize_seconds(seconds)}.", parse_mode=ParseMode.HTML
    )


async def _on_pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data["poll_state"].set_paused(True)
    await update.message.reply_text(
        "⏸ Automatic polling paused. /poll still works manually.", parse_mode=ParseMode.HTML
    )


async def _on_resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data["poll_state"].set_paused(False)
    await update.message.reply_text("▶️ Automatic polling resumed.", parse_mode=ParseMode.HTML)


async def _on_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    state = context.bot_data["poll_state"].get()
    status = "⏸ paused" if state.paused else "▶️ running"
    if state.last_poll_at is None:
        last = "never"
    else:
        last = f"{humanize_seconds(time.time() - state.last_poll_at)} ago"
    await update.message.reply_text(
        f"Status: {status}\n"
        f"Interval: {humanize_seconds(state.interval_seconds)}\n"
        f"Last poll: {last}",
        parse_mode=ParseMode.HTML,
    )


@dataclass
class _Command:
    name: str
    description: str
    handler: Callable[[Update, ContextTypes.DEFAULT_TYPE], object]


async def _on_new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data["answer_service"].reset_history()
    await update.message.reply_text("🆕 Started a new conversation.", parse_mode=ParseMode.HTML)


async def _on_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.bot_data["approvals"].list_pending()
    if not pending:
        await update.message.reply_text("No pending approvals.", parse_mode=ParseMode.HTML)
        return
    lines = [f"#{r.id}: {h(r.payload.get('draft', {}).get('summary', '?'))}" for r in pending]
    await update.message.reply_text(
        "Pending approvals:\n" + "\n".join(lines), parse_mode=ParseMode.HTML
    )


_COMMANDS = [
    _Command("new", "Start a fresh conversation, clearing chat history", _on_new),
    _Command("poll", "Manually trigger a mail poll right now", _on_poll),
    _Command("pending", "Show mails waiting for your approval", _on_pending),
    _Command("rules", "List active drafting rules", _on_rules),
    _Command("delete", "Delete Jira tickets: /delete SU-123 SU-456", _on_delete),
    _Command("interval", "Set poll interval: /interval 5m", _on_interval),
    _Command("pause", "Pause automatic polling", _on_pause),
    _Command("resume", "Resume automatic polling", _on_resume),
    _Command("status", "Show poll interval, paused state, and last poll time", _on_status),
]


async def _reflect_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data["reflection"].run()


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
        await app.bot.set_my_commands([(c.name, c.description) for c in _COMMANDS])
        await app.updater.start_polling()
        await server.serve()
        await app.updater.stop()
        await app.stop()
