from telegram.ext import Application, CommandHandler

from mailwright.telegram.commands import chat, help, jira, mail, memory, pending
from mailwright.telegram.commands.base import Domain, make_domain_dispatcher, require_auth

DOMAINS: list[Domain] = [mail.DOMAIN, jira.DOMAIN, memory.DOMAIN, chat.DOMAIN]


def bot_commands() -> list[tuple[str, str]]:
    cmds = [(d.name, d.description) for d in DOMAINS]
    cmds.append(("pending", pending.DESCRIPTION))
    cmds.append(("help", help.DESCRIPTION))
    return cmds


def agent_commands() -> list[tuple[str, str]]:
    cmds = []
    for d in DOMAINS:
        for a in d.actions:
            cmds.append((f"{d.name} {a.name}", a.description))
    cmds.append(("pending", pending.DESCRIPTION))
    cmds.append(("help", help.DESCRIPTION))
    return cmds


def register_handlers(app: Application) -> None:
    for d in DOMAINS:
        app.add_handler(CommandHandler(d.name, make_domain_dispatcher(d)))
    app.add_handler(CommandHandler("pending", require_auth(pending.on_pending)))
    app.add_handler(CommandHandler("help", require_auth(help.on_help)))
