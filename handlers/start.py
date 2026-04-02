import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CommandHandler, ContextTypes

from config import ADMIN_ID
from db import (
    add_user, get_user, get_text, replace_words_html,
    build_inline_keyboard, add_referral, get_referrer,
    has_accepted_terms,
)
from keyboards import currency_menu, main_menu, admin_panel
from utils import fmt_bal

log = logging.getLogger(__name__)

TERMS_TEXT = (
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📜 <b>شروط الاستخدام — متجر روز 🌹</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "• جميع العمليات رقمية ولا يمكن التراجع عنها بعد التنفيذ\n"
    "• الرصيد المُودَع غير قابل للسحب النقدي إلا عبر قسم السحب\n"
    "• يُمنع التلاعب أو استخدام أدوات خارجية أثناء الطلب\n"
    "• التعويض يُطبَّق وفق سياسة المتجر فقط\n"
    "• المتجر غير مسؤول عن أي خسائر بسبب بيانات خاطئة من المستخدم\n"
    "• يحق للإدارة تعليق أي حساب يثير الشبهات\n\n"
    "<i>بالضغط على ✅ موافق فأنت توافق على جميع الشروط أعلاه.</i>"
)


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u    = update.effective_user
    uid  = u.id
    name = u.first_name or "مستخدم"

    # ── الأدمن يرى لوحة الإدارة مباشرة ──────────────
    if uid == ADMIN_ID:
        add_user(uid, u.username or "", u.first_name or "")
        await update.message.reply_text(
            f"👑 <b>لوحة الإدارة</b>\nأهلاً {name}!",
            reply_markup=admin_panel(),
            parse_mode="HTML",
        )
        return

    # هل المستخدم جديد؟
    existing = get_user(uid)
    is_new   = (existing is None)

    add_user(uid, u.username or "", u.first_name or "")

    # ── تتبع الإحالة ──────────────────────────────────
    args        = ctx.args or []
    referrer_id = None
    if args:
        arg = args[0]
        if arg.startswith("ref_"):
            try:
                rid = int(arg[4:])
                if rid != uid:
                    add_referral(uid, rid)
                    referrer_id = rid
            except (ValueError, TypeError):
                pass

    user = get_user(uid)

    # ── إشعار الأدمن بعضو جديد ────────────────────────
    if is_new:
        uname_str = f"@{u.username}" if u.username else f"ID: {uid}"
        notif = (
            f"🆕 <b>عضو جديد انضم للبوت</b>\n"
            f"👤 {uname_str} | <code>{uid}</code>\n"
            f"📛 الاسم: {name}"
        )
        if referrer_id:
            notif += f"\n🔗 عبر إحالة: <code>{referrer_id}</code>"
        try:
            await ctx.bot.send_message(ADMIN_ID, notif, parse_mode="HTML")
        except Exception:
            pass

        # ── إشعار المُحيل ──────────────────────────────
        if referrer_id:
            try:
                await ctx.bot.send_message(
                    referrer_id,
                    f"🎉 <b>مبروك! انضم شخص جديد عبر رابطك!</b>\n\n"
                    f"👤 الاسم: <b>{name}</b>\n"
                    f"💡 ستحصل على عمولتك عند أول شراء يقوم به.\n\n"
                    f"<i>يمكنك متابعة إحالاتك من قسم نظام الأرباح 💸</i>",
                    parse_mode="HTML",
                )
                log.info(f"referral notification sent: new={uid} referrer={referrer_id}")
            except Exception as e:
                log.warning(f"referral notification failed for {referrer_id}: {e}")

    # ── فحص الشروط ────────────────────────────────────
    if not has_accepted_terms(uid):
        await update.message.reply_text(
            TERMS_TEXT,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ موافق على الشروط", callback_data="accept_terms")
            ]]),
        )
        return

    # ── عرض القائمة الرئيسية أو اختيار العملة ─────────
    if user and user.get("currency"):
        bal     = fmt_bal(user["balance"], user["currency"])
        welcome = get_text("welcome", "أهلاً بك في متجر روز 🌹")
        name_s  = replace_words_html(name)
        msg     = replace_words_html(
            f"{welcome}\n\nأهلاً <b>{name_s}</b> 👋\n💰 رصيدك: <b>{bal}</b>"
        )
        await update.message.reply_text(
            msg,
            reply_markup=main_menu(uid),
            parse_mode="HTML"
        )
        custom_kb = build_inline_keyboard()
        if custom_kb:
            await update.message.reply_text(
                "🎛 <b>القائمة المخصصة</b>",
                reply_markup=custom_kb,
                parse_mode="HTML"
            )
    else:
        await update.message.reply_text(
            "مرحباً عزيزي 👋\nاختر عملة حسابك:",
            reply_markup=currency_menu()
        )


start_handler = CommandHandler("start", start)
