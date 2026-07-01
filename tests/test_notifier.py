import asyncio

from mailwright.pipeline.message_service import OutgoingMessage
from mailwright.telegram.notifier import TelegramNotifier
from telegram.constants import ParseMode


class FakeSent:
    message_id = 4321


class FakeBot:
    def __init__(self):
        self.calls = []

    async def send_message(self, chat_id, text, reply_markup=None, parse_mode=None):
        self.calls.append((chat_id, text, reply_markup, parse_mode))
        return FakeSent()


class FakeApprovalRepo:
    def __init__(self):
        self.saved = []

    def set_tg_message_id(self, approval_id, message_id):
        self.saved.append((approval_id, message_id))


def test_send_plain_message_no_persist():
    bot, repo = FakeBot(), FakeApprovalRepo()
    n = TelegramNotifier(bot, "-100", repo)
    mid = asyncio.run(n.send(OutgoingMessage(text="hi")))
    assert mid == 4321
    assert bot.calls[0][0] == "-100" and bot.calls[0][2] is None
    assert bot.calls[0][3] == ParseMode.HTML
    assert repo.saved == []


def test_send_approval_card_persists_message_id():
    bot, repo = FakeBot(), FakeApprovalRepo()
    n = TelegramNotifier(bot, "-100", repo)
    msg = OutgoingMessage(text="card", buttons=[("✅ Approve", "act:approve:7")], approval_id=7)
    asyncio.run(n.send(msg))
    assert bot.calls[0][2] is not None  # reply_markup present
    assert bot.calls[0][3] == ParseMode.HTML
    assert repo.saved == [(7, 4321)]
