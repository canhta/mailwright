import html
import re


def md_to_html(text: str) -> str:
    """Escape HTML chars in LLM output, then convert **bold** and *italic* to HTML tags."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\*)\*(?!\*)([^\n*]+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    return text


def h(text: str) -> str:
    """Escape a dynamic string for safe embedding in a Telegram HTML message."""
    return html.escape(str(text))
