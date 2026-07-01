import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from mailwright.owa.session import OwaLoginRequired
from mailwright.pipeline.nudge_service import NudgeService
from mailwright.pipeline.summary_service import SummaryService
from mailwright.poller.scheduling import humanize_seconds, parse_duration, should_poll_now
from mailwright.telegram.dispatch import handle_callback
from mailwright.telegram.formatting import h, md_to_html
from mailwright.telegram.notifier import TelegramNotifier

log = logging.getLogger(__name__)

# How often the scheduled job wakes up to *check* whether a poll is due, per
# the persisted (and runtime-adjustable) poll_state interval. Not itself
# user-configurable — /interval below this has no effect.
HEARTBEAT_SECONDS = 30


async def _summary_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import datetime

    s = context.bot_data["settings"]
    svc = SummaryService(
        context.bot_data["processed"],
        context.bot_data["approvals"],
        context.bot_data["status_events"],
        s.summary_window_hours,
        text_escape=h,
    )
    await _notifier(context).send(svc.build(datetime.now()))


async def _nudge_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    from datetime import datetime

    s = context.bot_data["settings"]
    msg = NudgeService(context.bot_data["approvals"], s.nudge_stale_days, text_escape=h).build(
        datetime.now()
    )
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
    deletion_service = context.bot_data["deletion_service"]
    lines = []
    for key in keys:
        outcome = deletion_service.delete(key)
        if outcome.deleted:
            lines.append(f"🗑 Deleted {h(outcome.key)}")
        else:
            lines.append(f"❌ {h(outcome.key)}: {h(outcome.error)}")
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
    if seconds < HEARTBEAT_SECONDS:
        await update.message.reply_text(
            f"Minimum interval is {HEARTBEAT_SECONDS}s.", parse_mode=ParseMode.HTML
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


COMMANDS = [
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
