from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from db import get_user, set_currency, replace_words_html, get_text
from keyboards import main_menu, currency_menu, back
from utils import fmt_bal
from config import CURRENCY_NAMES, CURRENCY_SYMBOLS


async def handle_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    data = q.data

    # ── اختيار / تغيير العملة
    if data.startswith("cur_"):
        currency = data.split("_")[1]
        set_currency(uid, currency)
        user = get_user(uid)
        bal  = fmt_bal(user["balance"], currency)
        heading = get_text("main_menu", "القائمة الرئيسية 🌹")
        msg = replace_words_html(
            f"✅ العملة: <b>{CURRENCY_NAMES.get(currency, currency)}</b>\n\n"
            f"أهلاً <b>{q.from_user.first_name}</b> في {heading}\n"
            f"💰 رصيدك: <b>{bal}</b>"
        )
        await q.edit_message_text(msg, reply_markup=main_menu(uid), parse_mode="HTML")
        return

    if data == "change_currency":
        await q.edit_message_text("🔄 اختر العملة الجديدة:", reply_markup=currency_menu())
        return

    if data == "main_menu":
        user    = get_user(uid)
        bal     = fmt_bal(user["balance"], user["currency"] or "USD") if user else "0"
        heading = get_text("main_menu", "القائمة الرئيسية 🌹")
        msg     = replace_words_html(f"{heading}\n💰 رصيدك: <b>{bal}</b>")
        await q.edit_message_text(msg, reply_markup=main_menu(uid), parse_mode="HTML")
        return

    if data == "balance":
        user = get_user(uid)
        if not user:
            await q.answer("استخدم /start", show_alert=True)
            return
        bal = fmt_bal(user["balance"], user["currency"] or "USD")
        msg = replace_words_html(f"💰 <b>رصيدك الحالي</b>\n\n{bal}")
        await q.edit_message_text(msg, reply_markup=back(), parse_mode="HTML")
        return

    if data == "coupon":
        await q.edit_message_text(
            "🎁 <b>كود الخصم</b>\n\nأدخل كودك عند شراء أي خدمة للحصول على تخفيض.",
            reply_markup=back(), parse_mode="HTML"
        )
        return

menu_handler = CallbackQueryHandler(
    handle_menu,
    pattern="^(cur_|change_currency|main_menu|balance|coupon)"
)
