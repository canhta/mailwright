import uvicorn
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from mailwright.config import Settings
from mailwright.container import build_container
from mailwright.owa.state_store import write_state_file
from mailwright.pipeline.status_service import StatusReplyService
from mailwright.telegram.handlers import (
    COMMANDS,
    HEARTBEAT_SECONDS,
    _nudge_job,
    _on_callback,
    _on_text,
    _poll_job,
    _reflect_job,
    _summary_job,
)
from mailwright.telegram.notifier import TelegramNotifier
from mailwright.webhook.app import build_webhook_app


def build_agent(settings: Settings) -> Application:
    container = build_container(settings, commands=[(c.name, c.description) for c in COMMANDS])

    app = Application.builder().token(settings.telegram_bot_token).build()
    app.bot_data.update(
        {
            "settings": container.settings,
            "poller": container.poller,
            "poll_state": container.poll_state,
            "pipeline": container.pipeline,
            "approval_service": container.approval_service,
            "approvals": container.approvals,
            "processed": container.processed,
            "status_events": container.status_events,
            "owa": container.owa,
            "jira": container.jira,
            "episodic": container.episodic,
            "vector_store": container.vector_store,
            "thread_repo": container.thread_repo,
            "answer_service": container.answer_service,
            "reflection": container.reflection,
            "rulebook": container.rulebook,
            "deletion_service": container.deletion_service,
        }
    )
    app.add_handler(CallbackQueryHandler(_on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_text))
    for cmd in COMMANDS:
        app.add_handler(CommandHandler(cmd.name, cmd.handler))
    app.job_queue.run_repeating(_poll_job, interval=HEARTBEAT_SECONDS, first=5)
    from datetime import time as dtime

    hh, mm = (int(x) for x in settings.summary_time.split(":"))
    app.job_queue.run_daily(_summary_job, time=dtime(hour=hh, minute=mm))
    app.job_queue.run_daily(_nudge_job, time=dtime(hour=hh, minute=mm))
    app.job_queue.run_daily(_reflect_job, time=dtime(hour=2, minute=0))
    return app


async def run_agent(settings: Settings) -> None:
    app = build_agent(settings)
    status_service = StatusReplyService(
        app.bot_data["owa"],
        app.bot_data["thread_repo"],
        settings.status_targets,
        settings.jira_base_url,
        status_event_repo=app.bot_data["status_events"],
    )
    notifier = TelegramNotifier(app.bot, settings.telegram_chat_id, app.bot_data["approvals"])
    web = build_webhook_app(
        settings.webhook_secret,
        status_service,
        notifier.send,
        settings.owa_upload_secret,
        lambda state: write_state_file(settings.owa_state_path, state, settings.fernet_key),
    )
    config = uvicorn.Config(web, host="0.0.0.0", port=settings.webhook_port, log_level="info")
    server = uvicorn.Server(config)

    async with app:
        await app.start()
        await app.bot.set_my_commands([(c.name, c.description) for c in COMMANDS])
        await app.updater.start_polling()
        await server.serve()
        await app.updater.stop()
        await app.stop()
