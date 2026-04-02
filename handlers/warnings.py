"""
نظام الإنذارات — يتيح للأدمن إنذار المستخدمين عبر ID
إنذار 1 → رسالة تحذيرية
إنذار 2 → رسالة تحذيرية ثانية
إنذار 3 → حظر تلقائي فوري
"""
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters,
)

from config import ADMIN_ID
from db import get_user, get_warnings, warn_user, reset_warnings

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — —"

# حالات المحادثة
WARN_ENTER_UID = 80
WARN_ACTION    = 81


def _is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


def _warn_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة إنذار",        callback_data="warn_do_warn")],
        [InlineKeyboardButton("🔄 إعادة تعيين إنذارات", callback_data="warn_do_reset")],
        [InlineKeyboardButton("🔙 رجوع",               callback_data="admin_panel")],
    ])


# ═══════════════════════════════════════════════
# نقطة الدخول من لوحة الأدمن
# ═══════════════════════════════════════════════

async def warn_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """لوحة الإنذارات — يطلب ID المستخدم"""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    await q.edit_message_text(
        f"{SEP}\n⚠️ نظام الإنذارات\n{SEP2}\n"
        "أرسل <b>ID المستخدم</b> الذي تريد إنذاره أو عرض إنذاراته:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")],
        ]),
    )
    return WARN_ENTER_UID


async def warn_receive_uid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال ID المستخدم وعرض خياراته"""
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END

    raw = update.message.text.strip()
    if not raw.isdigit():
        await update.message.reply_text(
            "❌ أرسل ID رقمياً صحيحاً.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")],
            ]),
        )
        return WARN_ENTER_UID

    uid   = int(raw)
    user  = get_user(uid)
    warns = get_warnings(uid)

    if not user:
        await update.message.reply_text(
            f"❌ المستخدم <code>{uid}</code> غير مسجّل في البوت.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
            ]),
        )
        return ConversationHandler.END

    ctx.user_data["warn_uid"] = uid
    warn_bar = "⚠️" * warns + "⬜" * (3 - warns)
    status = "🚫 محظور" if user["is_banned"] else "✅ نشط"

    await update.message.reply_text(
        f"{SEP}\n⚠️ إنذارات المستخدم\n{SEP2}\n"
        f"👤 ID: <code>{uid}</code>\n"
        f"📛 الاسم: {user['username'] or '—'}\n"
        f"🔰 الحالة: {status}\n\n"
        f"عدد الإنذارات: <b>{warns}/3</b>  {warn_bar}\n\n"
        f"اختر الإجراء:",
        parse_mode="HTML",
        reply_markup=_warn_menu_kb(),
    )
    return WARN_ACTION


async def warn_do_warn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تنفيذ الإنذار"""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    uid = ctx.user_data.pop("warn_uid", None)
    if not uid:
        await q.edit_message_text("❌ انتهت الجلسة.")
        return ConversationHandler.END

    count, banned = warn_user(uid)

    # رسائل الإنذار للمستخدم
    warn_texts = {
        1: (
            f"{SEP}\n⚠️ إنذار أول\n{SEP2}\n"
            "لقد صدر بحقك إنذار تحذيري أول من إدارة المتجر.\n\n"
            "تنبّه: عند تجاوز 3 إنذارات سيتم <b>حظرك</b> تلقائياً من البوت."
        ),
        2: (
            f"{SEP}\n⚠️⚠️ إنذار ثانٍ\n{SEP2}\n"
            "هذا إنذارك <b>الثاني</b>. تبقّى لك إنذار واحد فقط.\n\n"
            "🚨 إنذار ثالث = <b>حظر فوري</b> من البوت."
        ),
    }

    if banned:
        user_msg = (
            f"{SEP}\n🚫 إنذار ثالث — تم الحظر\n{SEP2}\n"
            "تجاوزت الحد المسموح به من الإنذارات.\n"
            "تم <b>حظرك تلقائياً</b> من البوت بسبب المخالفات المتكررة."
        )
    else:
        user_msg = warn_texts.get(count, f"⚠️ تم إصدار إنذار #{count} بحقك.")

    try:
        await ctx.bot.send_message(uid, user_msg, parse_mode="HTML")
    except Exception:
        pass

    warn_bar = "⚠️" * count + "⬜" * (3 - count)
    admin_result = (
        f"{'🚫 تم الحظر تلقائياً!' if banned else f'✅ تم إصدار الإنذار #{count}'}\n"
        f"👤 المستخدم: <code>{uid}</code>\n"
        f"الإنذارات: <b>{count}/3</b>  {warn_bar}"
    )

    await q.edit_message_text(admin_result, parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")],
        ]),
    )
    return ConversationHandler.END


async def warn_do_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إعادة تعيين الإنذارات"""
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    uid = ctx.user_data.pop("warn_uid", None)
    if not uid:
        await q.edit_message_text("❌ انتهت الجلسة.")
        return ConversationHandler.END

    reset_warnings(uid)
    try:
        await ctx.bot.send_message(
            uid,
            f"{SEP}\n✅ تم إلغاء إنذاراتك\n{SEP2}\n"
            "تم إعادة تعيين إنذاراتك إلى الصفر من قِبل الإدارة.",
            parse_mode="HTML",
        )
    except Exception:
        pass

    await q.edit_message_text(
        f"✅ تم إعادة تعيين إنذارات المستخدم <code>{uid}</code> إلى الصفر.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")],
        ]),
    )
    return ConversationHandler.END


async def cancel_warn(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("warn_uid", None)
    if update.callback_query:
        await update.callback_query.answer()
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# تجميع الـ handlers
# ═══════════════════════════════════════════════

warn_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(warn_panel, pattern="^admin_warnings$")],
    states={
        WARN_ENTER_UID: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, warn_receive_uid),
            CallbackQueryHandler(cancel_warn, pattern="^admin_panel$"),
        ],
        WARN_ACTION: [
            CallbackQueryHandler(warn_do_warn,  pattern="^warn_do_warn$"),
            CallbackQueryHandler(warn_do_reset, pattern="^warn_do_reset$"),
            CallbackQueryHandler(cancel_warn,   pattern="^admin_panel$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_warn, pattern="^admin_panel$"),
        MessageHandler(filters.COMMAND, cancel_warn),
    ],
    per_message=False,
    allow_reentry=True,
)

warn_panel_handler = CallbackQueryHandler(warn_panel, pattern="^admin_warnings$")
