"""
ReplBot — نسخة موسّعة من ExtBot تُطبّق تغيير الكلمات على كل رسائل البوت تلقائياً.
"""
from telegram.ext import ExtBot


def _apply_rw(text, parse_mode=None):
    if not isinstance(text, str) or not text:
        return text
    try:
        from db import replace_words_html, replace_words
        return replace_words_html(text) if parse_mode == "HTML" else replace_words(text)
    except Exception:
        return text


class ReplBot(ExtBot):
    """ExtBot مع تغيير تلقائي للكلمات في send_message و edit_message_text."""

    async def send_message(self, chat_id, text=None, parse_mode=None, **kwargs):
        text = _apply_rw(text, parse_mode)
        return await super().send_message(
            chat_id, text=text, parse_mode=parse_mode, **kwargs
        )

    async def edit_message_text(self, text, *args, parse_mode=None, **kwargs):
        text = _apply_rw(text, parse_mode)
        return await super().edit_message_text(
            text, *args, parse_mode=parse_mode, **kwargs
        )
