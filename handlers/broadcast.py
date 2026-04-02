"""
نظام الإذاعة — متجر روز
━━━━━━━━━━━━━━━━━━━━━━━
الخطوة 1: اختر النوع → 📤 توجيه | 📝 نصية
الخطوة 2: أرسل الرسالة (نص/صورة/ملصق مميز/فيديو/GIF/أي نوع)
الخطوة 3: (نصية فقط) هل تريد زراً شفافاً؟
الخطوة 4: تأكيد → إرسال
"""

import asyncio
import logging

from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton,
    Message,
)
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters, CommandHandler,
)

from config import ADMIN_ID
from db import get_all_user_ids

log = logging.getLogger(__name__)

SEP  = "━━━━━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — — — —"

# ─── States ─────────────────────────────────────────────
BC_TYPE     = 0   # اختر: توجيه أم نصية
BC_WAIT     = 1   # انتظر الرسالة
BC_BTN      = 2   # هل تريد زر؟
BC_BTN_TEXT = 3   # نص الزر
BC_BTN_URL  = 4   # رابط الزر
BC_CONFIRM  = 5   # تأكيد الإرسال


def _is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ إلغاء", callback_data="bc_cancel")],
    ])


def _confirm_kb(extra_info: str = "") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ إرسال الآن", callback_data="bc_confirm"),
            InlineKeyboardButton("❌ إلغاء",      callback_data="bc_cancel"),
        ],
    ])


# ─── Entry: شاشة اختيار النوع ───────────────────────────
async def broadcast_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id if q else update.effective_user.id
    if not _is_admin(uid):
        return

    ctx.user_data.pop("bc", None)

    text = (
        f"{SEP}\n"
        "📢 <b>نظام الإذاعة</b>\n"
        f"{SEP2}\n\n"
        "اختر نوع الإذاعة:"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📤 إذاعة بالتوجيه", callback_data="bc_type_fwd"),
            InlineKeyboardButton("📝 إذاعة نصية",     callback_data="bc_type_text"),
        ],
        [InlineKeyboardButton("❌ إلغاء", callback_data="bc_cancel")],
    ])

    if q:
        await q.answer()
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)

    return BC_TYPE


# ─── اختيار النوع ───────────────────────────────────────
async def bc_type_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    mode = "forward" if q.data == "bc_type_fwd" else "text"
    ctx.user_data["bc"] = {
        "mode":      mode,
        "chat_id":    None,
        "message_id": None,
        "btn_label":  None,
        "btn_url":    None,
    }

    if mode == "forward":
        await q.edit_message_text(
            f"{SEP}\n"
            "📤 <b>إذاعة بالتوجيه</b>\n"
            f"{SEP2}\n\n"
            "وجّه أي رسالة تريد إذاعتها\n\n"
            "<i>• ستصل للمستخدمين بمعلومات المصدر الأصلي</i>\n"
            "<i>• تدعم كل أنواع الرسائل</i>",
            parse_mode="HTML",
            reply_markup=_cancel_kb(),
        )
    else:
        await q.edit_message_text(
            f"{SEP}\n"
            "📝 <b>إذاعة نصية</b>\n"
            f"{SEP2}\n\n"
            "أرسل رسالة الإذاعة:\n\n"
            "• نص / صورة / فيديو / ملصق مميز / GIF / صوت\n\n"
            "<i>💡 يمكنك إضافة زر شفاف تحت الرسالة</i>",
            parse_mode="HTML",
            reply_markup=_cancel_kb(),
        )

    return BC_WAIT


# ─── استقبال الرسالة ─────────────────────────────────────
async def receive_broadcast_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    msg: Message = update.message
    bc = ctx.user_data.get("bc", {})
    bc["chat_id"]    = msg.chat_id
    bc["message_id"] = msg.message_id
    ctx.user_data["bc"] = bc

    mode = bc.get("mode", "text")

    if mode == "forward":
        # توجيه — مباشرة للتأكيد
        await msg.reply_text(
            f"{SEP}\n"
            "📢 <b>تأكيد الإذاعة</b>\n"
            f"{SEP2}\n\n"
            "📤 طريقة الإرسال: <b>توجيه</b>\n"
            "الرسالة ستصل مع معلومات المصدر\n\n"
            "هل تريد الإرسال الآن؟",
            parse_mode="HTML",
            reply_markup=_confirm_kb(),
        )
        return BC_CONFIRM

    # نصية — اسأل عن الزر
    await msg.reply_text(
        "هل تريد إضافة <b>زر شفاف</b> تحت رسالة الإذاعة؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➕ إضافة زر", callback_data="bc_add_btn"),
                InlineKeyboardButton("⏭ بدون زر",  callback_data="bc_no_btn"),
            ],
            [InlineKeyboardButton("❌ إلغاء", callback_data="bc_cancel")],
        ]),
    )
    return BC_BTN


# ─── خيار الزر ──────────────────────────────────────────
async def bc_btn_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    if q.data == "bc_no_btn":
        await q.edit_message_text(
            f"{SEP}\n"
            "📢 <b>تأكيد الإذاعة</b>\n"
            f"{SEP2}\n\n"
            "📩 الرسالة جاهزة بدون زر إضافي\n\n"
            "هل تريد إرسالها الآن؟",
            parse_mode="HTML",
            reply_markup=_confirm_kb(),
        )
        return BC_CONFIRM

    await q.edit_message_text(
        "أرسل <b>نص الزر</b> الذي تريده:",
        parse_mode="HTML",
        reply_markup=_cancel_kb(),
    )
    return BC_BTN_TEXT


# ─── نص الزر ────────────────────────────────────────────
async def bc_receive_btn_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    ctx.user_data["bc"]["btn_label"] = update.message.text.strip()

    await update.message.reply_text(
        f"نص الزر: <b>{ctx.user_data['bc']['btn_label']}</b>\n\n"
        "أرسل الآن <b>رابط URL</b> للزر:\n"
        "<i>مثال: https://t.me/StoreRozbot</i>",
        parse_mode="HTML",
        reply_markup=_cancel_kb(),
    )
    return BC_BTN_URL


# ─── رابط الزر ──────────────────────────────────────────
async def bc_receive_btn_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    url = update.message.text.strip()
    bc  = ctx.user_data["bc"]
    bc["btn_url"] = url

    await update.message.reply_text(
        f"{SEP}\n"
        "📢 <b>تأكيد الإذاعة</b>\n"
        f"{SEP2}\n\n"
        f"🔘 الزر: <b>{bc['btn_label']}</b>\n"
        f"🔗 الرابط: <code>{url}</code>\n\n"
        "هل تريد الإرسال الآن؟",
        parse_mode="HTML",
        reply_markup=_confirm_kb(),
    )
    return BC_CONFIRM


# ─── تأكيد الإرسال ──────────────────────────────────────
async def bc_confirm_send(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    bc = ctx.user_data.pop("bc", None)
    if not bc or not bc.get("chat_id"):
        await q.edit_message_text("❌ انتهت الجلسة، ابدأ من جديد.")
        return ConversationHandler.END

    src_chat  = bc["chat_id"]
    src_msg   = bc["message_id"]
    mode      = bc.get("mode", "text")
    btn_label = bc.get("btn_label")
    btn_url   = bc.get("btn_url")

    reply_markup = None
    if mode == "text" and btn_label and btn_url:
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton(btn_label, url=btn_url)],
        ])

    users = get_all_user_ids()
    await q.edit_message_text(
        f"⏳ جاري الإرسال لـ <b>{len(users)}</b> مستخدم…",
        parse_mode="HTML",
    )

    success = 0
    for uid in users:
        try:
            if mode == "forward":
                await ctx.bot.forward_message(uid, src_chat, src_msg)
            else:
                await ctx.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=src_chat,
                    message_id=src_msg,
                    reply_markup=reply_markup,
                )
            success += 1
        except Exception:
            pass
        await asyncio.sleep(0.04)

    await q.message.reply_text(
        f"✅ <b>تمت الإذاعة</b>\n\n"
        f"📤 وصلت لـ <b>{success}</b> من <b>{len(users)}</b> مستخدم",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")],
        ]),
    )
    return ConversationHandler.END


# ─── إلغاء ──────────────────────────────────────────────
async def bc_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("bc", None)
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text(
            "❌ تم إلغاء الإذاعة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")],
            ]),
        )
    else:
        await update.message.reply_text("❌ تم إلغاء الإذاعة.")
    return ConversationHandler.END


# ─── ConversationHandler ────────────────────────────────
broadcast_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(broadcast_start, pattern="^admin_broadcast$"),
        CommandHandler("broadcast", broadcast_start),
    ],
    states={
        BC_TYPE: [
            CallbackQueryHandler(bc_type_choice, pattern="^bc_type_(fwd|text)$"),
            CallbackQueryHandler(bc_cancel,      pattern="^bc_cancel$"),
        ],
        BC_WAIT: [
            MessageHandler(filters.ALL & ~filters.COMMAND, receive_broadcast_msg),
            CallbackQueryHandler(bc_cancel, pattern="^bc_cancel$"),
        ],
        BC_BTN: [
            CallbackQueryHandler(bc_btn_choice, pattern="^bc_(add_btn|no_btn)$"),
            CallbackQueryHandler(bc_cancel,     pattern="^bc_cancel$"),
        ],
        BC_BTN_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, bc_receive_btn_text),
            CallbackQueryHandler(bc_cancel, pattern="^bc_cancel$"),
        ],
        BC_BTN_URL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, bc_receive_btn_url),
            CallbackQueryHandler(bc_cancel, pattern="^bc_cancel$"),
        ],
        BC_CONFIRM: [
            CallbackQueryHandler(bc_confirm_send, pattern="^bc_confirm$"),
            CallbackQueryHandler(bc_cancel,       pattern="^bc_cancel$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(bc_cancel, pattern="^bc_cancel$"),
        CallbackQueryHandler(bc_cancel, pattern="^admin_panel$"),
        MessageHandler(filters.COMMAND, bc_cancel),
    ],
    per_message=False,
    allow_reentry=True,
)
