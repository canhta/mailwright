from mailwright.pipeline.service import OutgoingMessage
from mailwright.telegram.markup import to_markup


class TelegramNotifier:
    def __init__(self, bot, chat_id: str, approval_repo) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._approval_repo = approval_repo

    async def send(self, message: OutgoingMessage) -> int:
        markup = to_markup(message.buttons) if message.buttons else None
        sent = await self._bot.send_message(self._chat_id, message.text, reply_markup=markup)
        if message.approval_id is not None:
            self._approval_repo.set_tg_message_id(message.approval_id, sent.message_id)
        return int(sent.message_id)
