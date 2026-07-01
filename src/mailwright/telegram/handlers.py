import asyncio
import contextlib
import logging
import time

from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import ContextTypes

from mailwright.owa.session import OwaLoginRequired
from mailwright.pipeline.nudge_service import NudgeService
from mailwright.pipeline.summary_service import SummaryService
from mailwright.poller.scheduling import should_poll_now
from mailwright.telegram.dispatch import handle_callback
from mailwright.telegram.formatting import h, md_to_html
from mailwright.telegram.notifier import TelegramNotifier

log = logging.getLogger(__name__)

# How often the scheduled job wakes up to *check* whether a poll is due, per
# the persisted (and runtime-adjustable) runtime_config interval. Not itself
# user-configurable — /mail interval below this has no effect.
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
    runtime_config = context.bot_data["runtime_config"]
    pipeline = context.bot_data["pipeline"]
    poller = context.bot_data["poller"]
    notifier = _notifier(context)
    runtime_config.mark_polled(time.time())
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
    state = context.bot_data["runtime_config"].get()
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


async def _reflect_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.bot_data["reflection"].run()
