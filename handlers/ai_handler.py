"""
AI Handler — متجر روز
━━━━━━━━━━━━━━━━━━━━━━
• مستخدم: وضع بيع + سوالف مع كشف مشبوه
• أدمن:   مساعد إداري + تلخيص مستخدمين + عرض محادثات + الأوامر
"""

import logging
import re

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters,
)

from db import is_banned, log_suspicious, get_suspicious_logs
from config import ADMIN_ID
import ai_agent
from rate_limit import rate_limit_ai, _is_allowed, AI_MAX, AI_WINDOW

log = logging.getLogger(__name__)
SEP  = "━━━━━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — — — —"

# ──────────────────────────────────────────────────────────
# حالة المستخدمين
# ──────────────────────────────────────────────────────────
_ai_active:       set[int] = set()
_admin_ai_active: set[int] = set()

# حالات Admin AI conv
ADM_AI_CHAT = 0

# صفحات المحادثة — عدد الرسائل لكل صفحة
_CONV_PAGE_SIZE = 6


def is_ai_active(uid: int) -> bool:
    return uid in _ai_active


def toggle_ai(uid: int) -> bool:
    if uid in _ai_active:
        _ai_active.discard(uid)
        # لا نمسح الذاكرة — تُستأنف المحادثة عند التفعيل مجدداً
        return False
    _ai_active.add(uid)
    return True


# ──────────────────────────────────────────────────────────
# بناء Inline Keyboard
# ──────────────────────────────────────────────────────────

def _build_kb(
    buttons: list[tuple[str, str]],
    include_menu: bool = False,
) -> InlineKeyboardMarkup | None:
    rows = []
    pair = []
    for label, cb in buttons:
        pair.append(InlineKeyboardButton(label, callback_data=cb))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    if include_menu:
        rows.append([
            InlineKeyboardButton("📋 القائمة",   callback_data="main_menu"),
            InlineKeyboardButton("💳 شحن رصيد", callback_data="deposit"),
        ])
    return InlineKeyboardMarkup(rows) if rows else None


# ──────────────────────────────────────────────────────────
# زر تفعيل/إيقاف AI (مستخدم)
# ──────────────────────────────────────────────────────────

async def toggle_ai_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    active = toggle_ai(uid)

    if active:
        history_len = ai_agent.get_session_len(uid)
        if history_len > 0:
            greeting = (
                f"{SEP}\n🤖 المساعد الذكي — شغّال!\n{SEP2}\n\n"
                "مرحباً! نكمل من حيث وقفنا 😊\n"
                "ذاكرتي معك كاملة، تفضل 🌹\n\n"
                "<i>اكتب /start ترجع للقائمة</i>"
            )
        else:
            greeting = (
                f"{SEP}\n🤖 المساعد الذكي — شغّال!\n{SEP2}\n\n"
                "هلا! أنا روزي، مساعد متجر روز 🌹\n"
                "كتب أي شيء: سعر، خدمة، أو بس سوالف 😄\n\n"
                "<i>اكتب /start ترجع للقائمة</i>"
            )
        await q.edit_message_text(
            greeting,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⏹ إيقاف المساعد", callback_data="ai_toggle"),
            ]]),
        )
    else:
        await q.edit_message_text(
            f"{SEP}\n💤 تم إيقاف المساعد\n{SEP2}\n\n"
            "شكراً، كان نيس! فعّلني متى تبي 😊",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("⬅️ القائمة", callback_data="main_menu"),
            ]]),
        )


# ──────────────────────────────────────────────────────────
# معالج رسائل AI (مستخدم)
# ──────────────────────────────────────────────────────────

def _user_in_any_conv(uid: int, app) -> bool:
    from telegram.ext import ConversationHandler as _CH
    try:
        for group_handlers in app.handlers.values():
            for h in group_handlers:
                if isinstance(h, _CH):
                    convs = getattr(h, "_conversations", {})
                    for key in list(convs.keys()):
                        if uid in key:
                            return True
    except Exception:
        pass
    return False


async def _alert_admin_suspicious(bot, uid: int, text: str):
    try:
        await bot.send_message(
            ADMIN_ID,
            f"⚠️ <b>تنبيه: نشاط مشبوه</b>\n\n"
            f"👤 المستخدم: <code>{uid}</code>\n"
            f"💬 الرسالة:\n<code>{text[:400]}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning("Failed to alert admin: %s", e)


async def ai_message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.text:
        return

    uid  = update.effective_user.id
    text = msg.text.strip()

    # ── حماية من السبام ──────────────────────────────
    if not _is_allowed("ai", uid, AI_MAX, AI_WINDOW):
        await msg.reply_text("⏳ روزي مشغولة قليلاً، أرسل رسالتك بعد ثوانٍ.")
        return

    if text.startswith("/"):
        return
    if is_banned(uid):
        return
    if _user_in_any_conv(uid, ctx.application):
        return

    if ai_agent.is_suspicious(text):
        log_suspicious(uid, text)
        await _alert_admin_suspicious(ctx.bot, uid, text)
        await msg.reply_text(
            "هذا ما أقدر أساعدك فيه 😄\n"
            "لو عندك سؤال عن الخدمات أو الأسعار، تفضل!",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📋 القائمة", callback_data="main_menu"),
            ]]),
        )
        return

    if not is_ai_active(uid):
        await msg.reply_text(
            "💡 فعّل <b>المساعد الذكي 🤖</b> وأجاوب على أسئلتك\n"
            "وأساعدك في أي خدمة تحتاجها 🔥",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🤖 تفعيل المساعد", callback_data="ai_toggle"),
                InlineKeyboardButton("📋 القائمة",        callback_data="main_menu"),
            ]]),
        )
        return

    await ctx.bot.send_chat_action(uid, ChatAction.TYPING)
    reply_text, buttons = await ai_agent.ai_reply(uid, text)
    mode = ai_agent.detect_mode(text)

    if buttons:
        kb = _build_kb(buttons, include_menu=(mode == "sales"))
    elif mode == "sales":
        kb = _build_kb([], include_menu=True)
    else:
        kb = None

    if kb:
        await msg.reply_text(reply_text, reply_markup=kb)
    else:
        await msg.reply_text(reply_text)


# ──────────────────────────────────────────────────────────
# مساعد الأدمن — شاشة الرئيسية
# ──────────────────────────────────────────────────────────

async def admin_ai_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    ai_agent.clear_admin_session(uid)
    ctx.user_data.pop("ai_target_uid", None)
    ctx.user_data.pop("conv_page", None)

    await q.edit_message_text(
        f"{SEP}\n🤖 <b>مساعد الأدمن الذكي</b>\n{SEP2}\n\n"
        "اسألني أي شيء أو ابحث عن مستخدم 💼\n\n"
        "للبحث عن مستخدم أرسل:\n"
        "<code>لخص [ID المستخدم]</code>\n"
        "مثال: <code>لخص 123456789</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚠️ الرسائل المشبوهة", callback_data="admin_ai_suspicious")],
            [
                InlineKeyboardButton("🧹 مسح المحادثة", callback_data="admin_ai_clear"),
                InlineKeyboardButton("🔙 لوحة التحكم",  callback_data="admin_panel"),
            ],
        ]),
    )
    return ADM_AI_CHAT


# ──────────────────────────────────────────────────────────
# عرض الرسائل المشبوهة
# ──────────────────────────────────────────────────────────

async def admin_ai_suspicious_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    rows = get_suspicious_logs(15)
    if not rows:
        await q.answer("✅ لا توجد رسائل مشبوهة", show_alert=True)
        return ADM_AI_CHAT

    lines = [f"{SEP}\n⚠️ <b>آخر الرسائل المشبوهة</b>\n{SEP2}"]
    for r in rows:
        lines.append(
            f"\n👤 <code>{r['user_id']}</code> — {r['logged_at']}\n"
            f"💬 <code>{r['message'][:200]}</code>"
        )

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"

    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_ai")],
        ]),
    )
    return ADM_AI_CHAT


# ──────────────────────────────────────────────────────────
# معالج نص الأدمن (لخص / دردشة عادية)
# ──────────────────────────────────────────────────────────

async def admin_ai_chat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid != ADMIN_ID:
        return ConversationHandler.END

    text = (update.message.text or "").strip()
    if not text:
        return ADM_AI_CHAT

    m = re.match(r"^لخص\s+(\d+)$", text)
    if m:
        target = int(m.group(1))
        ctx.user_data["ai_target_uid"] = target
        ctx.user_data.pop("conv_page", None)

        from db import get_user_activity_summary
        data = get_user_activity_summary(target)
        if not data:
            await update.message.reply_text(
                f"❌ ما في مستخدم بالـ ID: <code>{target}</code>",
                parse_mode="HTML",
            )
            return ADM_AI_CHAT

        uname    = data.get("username") or "—"
        balance  = data.get("balance", 0)
        orders_n = len(data.get("orders", []))
        warns    = data.get("warnings", 0)
        banned   = "🚫 محظور" if data.get("is_banned") else "✅ نشط"

        await update.message.reply_text(
            f"{SEP}\n👤 <b>المستخدم {target}</b>\n{SEP2}\n\n"
            f"👤 الاسم: @{uname}\n"
            f"💰 الرصيد: <b>{balance:.2f}$</b>\n"
            f"📦 الطلبات: <b>{orders_n}</b>\n"
            f"⚠️ الإنذارات: <b>{warns}</b>\n"
            f"🔘 الحالة: {banned}\n\n"
            "اختر ما تريد معرفته:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📜 كشف المحادثات",    callback_data="admin_ai_conv_view"),
                    InlineKeyboardButton("📋 الأوامر المستخدمة", callback_data="admin_ai_cmds"),
                ],
                [
                    InlineKeyboardButton("📊 لخص النشاط",    callback_data="admin_ai_sum_act"),
                ],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_ai")],
            ]),
        )
        return ADM_AI_CHAT

    await ctx.bot.send_chat_action(uid, ChatAction.TYPING)
    reply = await ai_agent.ai_admin_reply(uid, text)

    await update.message.reply_text(
        reply,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel"),
                InlineKeyboardButton("🧹 مسح المحادثة", callback_data="admin_ai_clear"),
            ],
        ]),
    )
    return ADM_AI_CHAT


# ──────────────────────────────────────────────────────────
# 📜 عارض المحادثات — مع ترقيم الصفحات
# ──────────────────────────────────────────────────────────

def _format_conv_page(history: list[dict], page: int) -> tuple[str, int, int]:
    """يُرجع (النص، الصفحة الحالية، إجمالي الصفحات)."""
    total_pages = max(1, -(-len(history) // _CONV_PAGE_SIZE))  # ceiling division
    page = max(0, min(page, total_pages - 1))

    start = page * _CONV_PAGE_SIZE
    chunk = history[start: start + _CONV_PAGE_SIZE]

    lines = [
        f"{SEP}\n📜 <b>محادثات المستخدم مع روزي</b>\n"
        f"الصفحة {page + 1} / {total_pages}\n{SEP2}\n"
    ]

    for msg in chunk:
        role = "👤 المستخدم" if msg["role"] == "user" else "🤖 روزي"
        content = msg["content"][:300]
        if len(msg["content"]) > 300:
            content += "…"
        lines.append(f"\n{role}:\n{content}")

    return "\n".join(lines), page, total_pages


def _conv_nav_kb(page: int, total_pages: int, target: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ السابق", callback_data="admin_ai_conv_prev"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️ التالي", callback_data="admin_ai_conv_next"))

    rows = []
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton("📊 تلخيص المحادثات", callback_data="admin_ai_sum_chat"),
    ])
    rows.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="admin_ai"),
    ])
    return InlineKeyboardMarkup(rows)


async def admin_ai_view_conv_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """📜 كشف المحادثات — الصفحة الأولى"""
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    target = ctx.user_data.get("ai_target_uid")
    if not target:
        await q.edit_message_text("❌ لا يوجد مستخدم محدد. أرسل <code>لخص [ID]</code> أولاً.", parse_mode="HTML")
        return ADM_AI_CHAT

    from db import get_ai_history
    history = get_ai_history(target)

    if not history:
        await q.edit_message_text(
            f"📜 المستخدم <code>{target}</code> لم يتحدث مع روزي بعد.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_ai")],
            ]),
        )
        return ADM_AI_CHAT

    ctx.user_data["conv_page"] = 0
    text, page, total = _format_conv_page(history, 0)

    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=_conv_nav_kb(page, total, target),
    )
    return ADM_AI_CHAT


async def admin_ai_conv_next_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """➡️ الصفحة التالية"""
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    target = ctx.user_data.get("ai_target_uid")
    if not target:
        return ADM_AI_CHAT

    from db import get_ai_history
    history  = get_ai_history(target)
    cur_page = ctx.user_data.get("conv_page", 0) + 1
    text, page, total = _format_conv_page(history, cur_page)
    ctx.user_data["conv_page"] = page

    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=_conv_nav_kb(page, total, target),
    )
    return ADM_AI_CHAT


async def admin_ai_conv_prev_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """⬅️ الصفحة السابقة"""
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    target = ctx.user_data.get("ai_target_uid")
    if not target:
        return ADM_AI_CHAT

    from db import get_ai_history
    history  = get_ai_history(target)
    cur_page = max(0, ctx.user_data.get("conv_page", 0) - 1)
    text, page, total = _format_conv_page(history, cur_page)
    ctx.user_data["conv_page"] = page

    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=_conv_nav_kb(page, total, target),
    )
    return ADM_AI_CHAT


# ──────────────────────────────────────────────────────────
# 📋 الأوامر المستخدمة داخل البوت
# ──────────────────────────────────────────────────────────

async def admin_ai_cmds_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """📋 عرض كل الأوامر/الخدمات التي استخدمها المستخدم"""
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    target = ctx.user_data.get("ai_target_uid")
    if not target:
        await q.edit_message_text("❌ لا يوجد مستخدم محدد. أرسل <code>لخص [ID]</code> أولاً.", parse_mode="HTML")
        return ADM_AI_CHAT

    from db import get_user_activity_summary
    data = get_user_activity_summary(target)

    lines = [f"{SEP}\n📋 <b>نشاط المستخدم {target}</b>\n{SEP2}\n"]

    orders = data.get("orders", []) if data else []
    if orders:
        lines.append("📦 <b>الطلبات:</b>")
        for i, o in enumerate(orders[:30], 1):
            svc    = o.get("service", "—")
            status = o.get("status", "—")
            amount = o.get("amount")
            date   = str(o.get("created_at", ""))[:10]
            amt_str = f" · {amount:.2f}$" if amount else ""
            lines.append(f"  {i}. {svc} — {status}{amt_str} <i>({date})</i>")
    else:
        lines.append("📦 لا توجد طلبات مسجّلة.")

    # تذاكر الدعم إن وُجدت
    tickets = data.get("tickets", []) if data else []
    if tickets:
        lines.append("\n🎫 <b>تذاكر الدعم:</b>")
        for t in tickets[:10]:
            subj   = t.get("subject") or t.get("service") or "—"
            status = t.get("status", "—")
            date   = str(t.get("created_at", ""))[:10]
            lines.append(f"  • {subj} — {status} <i>({date})</i>")

    # إيداعات
    deposits = data.get("deposits", []) if data else []
    if deposits:
        lines.append("\n💳 <b>الإيداعات:</b>")
        for d in deposits[:10]:
            method = d.get("method") or d.get("type") or "—"
            amount = d.get("amount", 0)
            date   = str(d.get("created_at", ""))[:10]
            lines.append(f"  • {method} — {amount:.2f}$ <i>({date})</i>")

    if not orders and not tickets and not deposits:
        lines.append("\n⚠️ لا يوجد أي نشاط مسجّل لهذا المستخدم.")

    text = "\n".join(lines)
    if len(text) > 3900:
        text = text[:3900] + "\n…"

    await q.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 لخص النشاط", callback_data="admin_ai_sum_act")],
            [InlineKeyboardButton("🔙 رجوع",        callback_data="admin_ai")],
        ]),
    )
    return ADM_AI_CHAT


# ──────────────────────────────────────────────────────────
# 📊 تلخيص النشاط
# ──────────────────────────────────────────────────────────

async def admin_ai_sum_activity_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer("⏳ جاري التحليل…")

    target = ctx.user_data.get("ai_target_uid")
    if not target:
        await q.edit_message_text("❌ لا يوجد مستخدم محدد.", parse_mode="HTML")
        return ADM_AI_CHAT

    await ctx.bot.send_chat_action(uid, ChatAction.TYPING)
    summary = await ai_agent.summarize_user(target)

    await q.edit_message_text(
        f"📊 <b>ملخص نشاط المستخدم {target}</b>\n{SEP2}\n\n{summary}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📜 كشف المحادثات",    callback_data="admin_ai_conv_view"),
                InlineKeyboardButton("📋 الأوامر المستخدمة", callback_data="admin_ai_cmds"),
            ],
            [InlineKeyboardButton("💬 لخص المحادثات",      callback_data="admin_ai_sum_chat")],
            [InlineKeyboardButton("🔙 رجوع",                callback_data="admin_ai")],
        ]),
    )
    return ADM_AI_CHAT


# ──────────────────────────────────────────────────────────
# 💬 تلخيص محادثات AI
# ──────────────────────────────────────────────────────────

async def admin_ai_sum_chat_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer("⏳ جاري التحليل…")

    target = ctx.user_data.get("ai_target_uid")
    if not target:
        await q.edit_message_text("❌ لا يوجد مستخدم محدد.", parse_mode="HTML")
        return ADM_AI_CHAT

    await ctx.bot.send_chat_action(uid, ChatAction.TYPING)
    summary = await ai_agent.summarize_user_chat(target)

    await q.edit_message_text(
        f"💬 <b>ملخص محادثات المستخدم {target} مع روزي</b>\n{SEP2}\n\n{summary}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📜 كشف المحادثات",    callback_data="admin_ai_conv_view"),
                InlineKeyboardButton("📋 الأوامر المستخدمة", callback_data="admin_ai_cmds"),
            ],
            [InlineKeyboardButton("📊 لخص النشاط",          callback_data="admin_ai_sum_act")],
            [InlineKeyboardButton("🔙 رجوع",                callback_data="admin_ai")],
        ]),
    )
    return ADM_AI_CHAT


# ──────────────────────────────────────────────────────────
# مسح / خروج
# ──────────────────────────────────────────────────────────

async def admin_ai_clear(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer("✅ تم مسح المحادثة")
    ai_agent.clear_admin_session(uid)
    return await admin_ai_start(update, ctx)


async def admin_ai_exit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ai_agent.clear_admin_session(q.from_user.id)
    return ConversationHandler.END


# ──────────────────────────────────────────────────────────
# Handlers
# ──────────────────────────────────────────────────────────

ai_toggle_handler = CallbackQueryHandler(toggle_ai_cb, pattern="^ai_toggle$")
ai_text_handler   = MessageHandler(filters.TEXT & ~filters.COMMAND, ai_message_handler)

admin_ai_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(admin_ai_start, pattern="^admin_ai$"),
    ],
    states={
        ADM_AI_CHAT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ai_chat),
            # الرسائل المشبوهة
            CallbackQueryHandler(admin_ai_suspicious_cb,    pattern="^admin_ai_suspicious$"),
            # عارض المحادثات
            CallbackQueryHandler(admin_ai_view_conv_cb,     pattern="^admin_ai_conv_view$"),
            CallbackQueryHandler(admin_ai_conv_next_cb,     pattern="^admin_ai_conv_next$"),
            CallbackQueryHandler(admin_ai_conv_prev_cb,     pattern="^admin_ai_conv_prev$"),
            # الأوامر المستخدمة
            CallbackQueryHandler(admin_ai_cmds_cb,          pattern="^admin_ai_cmds$"),
            # التلخيص
            CallbackQueryHandler(admin_ai_sum_activity_cb,  pattern="^admin_ai_sum_act$"),
            CallbackQueryHandler(admin_ai_sum_chat_cb,      pattern="^admin_ai_sum_chat$"),
            # مسح / خروج
            CallbackQueryHandler(admin_ai_clear,            pattern="^admin_ai_clear$"),
            CallbackQueryHandler(admin_ai_exit,             pattern="^admin_panel$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(admin_ai_exit, pattern="^admin_panel$"),
    ],
    per_message=False,
    allow_reentry=True,
)

admin_ai_suspicious_handler = CallbackQueryHandler(
    admin_ai_suspicious_cb, pattern="^admin_ai_suspicious$"
)
