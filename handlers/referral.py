from telegram import Update, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler, ContextTypes

from db import get_ref_count, get_ref_percent
from keyboards import make_btn as MB

SEP  = "━━━━━━━━━━━━━━━"
SEP2 = "───────────────"


async def referral_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = q.from_user

    count   = get_ref_count(u.id)
    percent = get_ref_percent()
    bot_name = ctx.bot.username
    link    = f"https://t.me/{bot_name}?start=ref_{u.id}"

    await q.edit_message_text(
        f"{SEP}\n💸 نظام الأرباح\n{SEP}\n\n"
        f"🔗 <b>رابطك الخاص:</b>\n"
        f"<code>{link}</code>\n\n"
        f"{SEP2}\n"
        f"👥 إجمالي المُحالين: <b>{count}</b>\n"
        f"💰 نسبة العمولة: <b>{percent:.1f}%</b>\n\n"
        f"📌 <b>كيف يعمل؟</b>\n"
        f"شارك رابطك مع أصدقائك، وعندما يقوم أحدهم\n"
        f"بشحن رصيده ستحصل تلقائياً على <b>{percent:.1f}%</b> من المبلغ! 🔥",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            MB("⬅️ رجوع", "back_main", "btn_back")
        ]])
    )


referral_handler = CallbackQueryHandler(referral_menu, pattern="^referral$")
