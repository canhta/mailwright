# src/mailwright/telegram/commands/memory.py
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from mailwright.telegram.commands.base import Action, Domain
from mailwright.telegram.formatting import h


async def _on_rules(update: Update, context: ContextTypes.DEFAULT_TYPE, args: list[str]) -> None:
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
        f"Active rules:\n{active_str}\n\nProposed (use /memory rules approve ID):\n{proposed_str}",
        parse_mode=ParseMode.HTML,
    )


DOMAIN = Domain(
    name="memory",
    description="Drafting rules learned from your approvals/edits",
    actions=[
        Action(
            "rules",
            "List active/proposed drafting rules: /memory rules approve ID",
            _on_rules,
        ),
    ],
)
