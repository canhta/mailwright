from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def to_markup(buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=label, callback_data=data) for label, data in buttons]
    return InlineKeyboardMarkup([row])
