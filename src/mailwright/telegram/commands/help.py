from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from mailwright.telegram.formatting import h

DESCRIPTION = "Show all available commands"


async def on_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from mailwright.telegram.commands import agent_commands

    lines = [f"/{name} — {h(desc)}" for name, desc in agent_commands()]
    await update.message.reply_text(
        "Available commands:\n" + "\n".join(lines), parse_mode=ParseMode.HTML
    )
