import time

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from mailwright.poller.scheduling import humanize_seconds, parse_duration
from mailwright.telegram.commands.base import Action, Domain
from mailwright.telegram.formatting import h
from mailwright.telegram.handlers import HEARTBEAT_SECONDS, _run_poll_once

_CONFIG_USAGE = h(
    "Usage:\n"
    "/mail config reply_all <on|off>\n"
    "/mail config urgent_ping <on|off>\n"
    "/mail config senders <list|add|remove> [entry]"
)


async def _on_poll(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    await update.message.reply_text("Polling now...", parse_mode=ParseMode.HTML)
    await _run_poll_once(context)
    await update.message.reply_text("Done.", parse_mode=ParseMode.HTML)


async def _on_pause(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    context.bot_data["runtime_config"].set_paused(True)
    await update.message.reply_text(
        "⏸ Automatic polling paused. /mail poll still works manually.", parse_mode=ParseMode.HTML
    )


async def _on_resume(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    context.bot_data["runtime_config"].set_paused(False)
    await update.message.reply_text("▶️ Automatic polling resumed.", parse_mode=ParseMode.HTML)


async def _on_interval(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    if not args:
        await update.message.reply_text(
            "Usage: /mail interval 5m (also accepts e.g. 300, 45s, 2h)", parse_mode=ParseMode.HTML
        )
        return
    try:
        seconds = parse_duration(args[0])
    except ValueError as exc:
        await update.message.reply_text(h(str(exc)), parse_mode=ParseMode.HTML)
        return
    if seconds < HEARTBEAT_SECONDS:
        await update.message.reply_text(
            f"Minimum interval is {HEARTBEAT_SECONDS}s.", parse_mode=ParseMode.HTML
        )
        return
    context.bot_data["runtime_config"].set_interval(seconds)
    await update.message.reply_text(
        f"Poll interval set to {humanize_seconds(seconds)}.", parse_mode=ParseMode.HTML
    )


async def _on_status(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    state = context.bot_data["runtime_config"].get()
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


def _parse_on_off(text: str) -> bool | None:
    t = text.strip().lower()
    if t == "on":
        return True
    if t == "off":
        return False
    return None


async def _on_config_senders(
    update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]
) -> None:
    cfg_repo = context.bot_data["runtime_config"]
    if not args:
        await update.message.reply_text(
            h("Usage: /mail config senders <list|add|remove> [entry]"), parse_mode=ParseMode.HTML
        )
        return
    sub = args[0].lower()
    if sub == "list":
        senders = ", ".join(cfg_repo.get().sender_allowlist) or "(none)"
        await update.message.reply_text(
            f"Sender allowlist: {h(senders)}", parse_mode=ParseMode.HTML
        )
        return
    if sub in ("add", "remove"):
        if len(args) < 2:
            await update.message.reply_text(
                h(f"Usage: /mail config senders {sub} <email-or-domain>"),
                parse_mode=ParseMode.HTML,
            )
            return
        entry = args[1]
        if sub == "add":
            cfg_repo.add_sender(entry)
            await update.message.reply_text(
                f"Added {h(entry.strip().lower())} to sender allowlist.", parse_mode=ParseMode.HTML
            )
        else:
            cfg_repo.remove_sender(entry)
            await update.message.reply_text(
                f"Removed {h(entry.strip().lower())} from sender allowlist.",
                parse_mode=ParseMode.HTML,
            )
        return
    await update.message.reply_text(
        h("Usage: /mail config senders <list|add|remove> [entry]"), parse_mode=ParseMode.HTML
    )


async def _on_config(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    cfg_repo = context.bot_data["runtime_config"]
    if not args:
        cfg = cfg_repo.get()
        senders = ", ".join(cfg.sender_allowlist) or "(none)"
        await update.message.reply_text(
            f"Reply-all on ticket creation: {'ON' if cfg.reply_all_enabled else 'OFF'}\n"
            f"Urgent escalation ping: {'ON' if cfg.urgent_ping_enabled else 'OFF'}\n"
            f"Sender allowlist: {h(senders)}\n\n{_CONFIG_USAGE}",
            parse_mode=ParseMode.HTML,
        )
        return
    key = args[0].lower()
    if key == "reply_all":
        val = _parse_on_off(args[1]) if len(args) > 1 else None
        if val is None:
            await update.message.reply_text(
                h("Usage: /mail config reply_all <on|off>"), parse_mode=ParseMode.HTML
            )
            return
        cfg_repo.set_reply_all(val)
        await update.message.reply_text(
            f"Reply-all on ticket creation: {'ON' if val else 'OFF'}", parse_mode=ParseMode.HTML
        )
        return
    if key == "urgent_ping":
        val = _parse_on_off(args[1]) if len(args) > 1 else None
        if val is None:
            await update.message.reply_text(
                h("Usage: /mail config urgent_ping <on|off>"), parse_mode=ParseMode.HTML
            )
            return
        cfg_repo.set_urgent_ping(val)
        await update.message.reply_text(
            f"Urgent escalation ping: {'ON' if val else 'OFF'}", parse_mode=ParseMode.HTML
        )
        return
    if key == "senders":
        await _on_config_senders(update, context, args[1:])
        return
    await update.message.reply_text(_CONFIG_USAGE, parse_mode=ParseMode.HTML)


DOMAIN = Domain(
    name="mail",
    description="Mail polling and pipeline settings",
    actions=[
        Action("poll", "Manually trigger a mail poll right now", _on_poll),
        Action("pause", "Pause automatic polling", _on_pause),
        Action("resume", "Resume automatic polling", _on_resume),
        Action("interval", "Set poll interval: /mail interval 5m", _on_interval),
        Action("status", "Show poll interval, paused state, and last poll time", _on_status),
        Action(
            "config",
            "Show/set reply-all, urgent-ping, and sender-allowlist toggles",
            _on_config,
        ),
    ],
)
