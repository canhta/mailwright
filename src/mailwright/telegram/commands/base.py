from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from mailwright.telegram.auth import is_authorized
from mailwright.telegram.formatting import h

NOT_AUTHORIZED_TEXT = "🔒 Not authorized."

ActionHandler = Callable[[Update, ContextTypes.DEFAULT_TYPE, list[str]], Awaitable[None]]
CommandHandlerFn = Callable[[Update, ContextTypes.DEFAULT_TYPE], Awaitable[None]]


@dataclass
class Action:
    name: str
    description: str
    handler: ActionHandler


@dataclass
class Domain:
    name: str
    description: str
    actions: list[Action]


def find_action(domain: Domain, name: str) -> Action | None:
    name = name.lower()
    return next((a for a in domain.actions if a.name == name), None)


def usage_text(domain: Domain) -> str:
    names = "|".join(a.name for a in domain.actions)
    return h(f"Usage: /{domain.name} <{names}>")


def is_authorized_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings = context.bot_data["settings"]
    return is_authorized(update.effective_user.id, settings.telegram_allowlist)


def require_auth(handler: CommandHandlerFn) -> CommandHandlerFn:
    async def _wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_authorized_update(update, context):
            await update.message.reply_text(NOT_AUTHORIZED_TEXT)
            return
        await handler(update, context)

    return _wrapped


def make_domain_dispatcher(domain: Domain) -> CommandHandlerFn:
    async def _dispatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not is_authorized_update(update, context):
            await update.message.reply_text(NOT_AUTHORIZED_TEXT)
            return
        args = context.args
        if not args:
            await update.message.reply_text(usage_text(domain), parse_mode=ParseMode.HTML)
            return
        action = find_action(domain, args[0])
        if action is None:
            await update.message.reply_text(usage_text(domain), parse_mode=ParseMode.HTML)
            return
        await action.handler(update, context, args[1:])

    return _dispatch
