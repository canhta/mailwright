from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from mailwright.telegram.commands.base import Action, Domain


async def _on_new(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    context.bot_data["answer_service"].reset_history()
    await update.message.reply_text("🆕 Started a new conversation.", parse_mode=ParseMode.HTML)


DOMAIN = Domain(
    name="chat",
    description="Conversation controls",
    actions=[
        Action("new", "Start a fresh conversation, clearing chat history", _on_new),
    ],
)
