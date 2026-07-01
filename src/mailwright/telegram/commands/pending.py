from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from mailwright.telegram.formatting import h

DESCRIPTION = "Show mails waiting for your approval"


async def on_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending = context.bot_data["approvals"].list_pending()
    if not pending:
        await update.message.reply_text("No pending approvals.", parse_mode=ParseMode.HTML)
        return
    lines = [f"#{r.id}: {h(r.payload.get('draft', {}).get('summary', '?'))}" for r in pending]
    await update.message.reply_text(
        "Pending approvals:\n" + "\n".join(lines), parse_mode=ParseMode.HTML
    )
