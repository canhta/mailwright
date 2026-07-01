from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from mailwright.telegram.commands.base import Action, Domain
from mailwright.telegram.formatting import h


async def _on_delete(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
    if not args:
        await update.message.reply_text(
            "Usage: /jira delete SU-123 SU-456", parse_mode=ParseMode.HTML
        )
        return
    deletion_service = context.bot_data["deletion_service"]
    lines = []
    for key in args:
        outcome = deletion_service.delete(key)
        if outcome.deleted:
            lines.append(f"🗑 Deleted {h(outcome.key)}")
        else:
            lines.append(f"❌ {h(outcome.key)}: {h(outcome.error)}")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


DOMAIN = Domain(
    name="jira",
    description="Jira ticket actions",
    actions=[
        Action("delete", "Delete Jira tickets: /jira delete SU-123 SU-456", _on_delete),
    ],
)
