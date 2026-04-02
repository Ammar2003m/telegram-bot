"""
حماية من السبام — Rate Limiting بسيط (في الذاكرة)
لكل مستخدم: max N رسالة/نقرة في الفترة الزمنية window_sec
"""
import time
from collections import defaultdict, deque
from functools import wraps
from typing import Callable

from telegram import Update
from telegram.ext import ContextTypes

# ── إعدادات السرعة المسموح بها ──────────────────────
BUTTON_MAX    = 5     # أقصى عدد ضغطات زر / 5 ثواني
BUTTON_WINDOW = 5

AI_MAX        = 2     # أقصى رسائل AI / 6 ثواني
AI_WINDOW     = 6

MSG_MAX       = 10    # أقصى رسائل نصية / 10 ثواني
MSG_WINDOW    = 10

# ── مخزن الطوابع الزمنية (user_id → deque of timestamps) ─────
_stores: dict[str, dict[int, deque]] = defaultdict(lambda: defaultdict(deque))


def _is_allowed(bucket: str, uid: int, max_calls: int, window: float) -> bool:
    store = _stores[bucket]
    now   = time.monotonic()
    q     = store[uid]
    # نزيل الطوابع القديمة
    while q and q[0] < now - window:
        q.popleft()
    if len(q) >= max_calls:
        return False
    q.append(now)
    return True


def rate_limit_button(max_calls: int = BUTTON_MAX, window: float = BUTTON_WINDOW):
    """مزخرف للمعالجات التي تستقبل CallbackQuery."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            q = update.callback_query
            if q is None:
                return await func(update, ctx)
            uid = q.from_user.id
            if not _is_allowed("btn", uid, max_calls, window):
                await q.answer("⚠️ أنت تضغط بسرعة كبيرة، انتظر لحظة.", show_alert=True)
                return
            return await func(update, ctx)
        return wrapper
    return decorator


def rate_limit_message(max_calls: int = MSG_MAX, window: float = MSG_WINDOW):
    """مزخرف للمعالجات التي تستقبل رسائل نصية عادية."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            msg = update.effective_message
            uid = update.effective_user.id if update.effective_user else None
            if uid and not _is_allowed("msg", uid, max_calls, window):
                if msg:
                    await msg.reply_text("⚠️ أنت ترسل بسرعة كبيرة، انتظر لحظة.")
                return
            return await func(update, ctx)
        return wrapper
    return decorator


def rate_limit_ai(max_calls: int = AI_MAX, window: float = AI_WINDOW):
    """مزخرف خاص بالذكاء الاصطناعي — أقل تسامحاً."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
            uid = update.effective_user.id if update.effective_user else None
            if uid and not _is_allowed("ai", uid, max_calls, window):
                msg = update.effective_message
                if msg:
                    await msg.reply_text("⏳ روزي مشغولة قليلاً، أرسل رسالتك بعد ثوانٍ.")
                return
            return await func(update, ctx)
        return wrapper
    return decorator
