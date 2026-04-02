from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler, ContextTypes

from db import get_user, get_text, replace_words_html
from keyboards import main_menu, make_btn as MB, admin_edit_row
from utils import fmt_bal

SEP = "━━━━━━━━━━━━━━━"


async def services_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    rows = [
        [
            MB("خدمات تيليجرامية 🟦",    "telegram_services", "btn_svc_telegram"),
            MB("خدمات عامة 🌐",           "general",           "btn_svc_general"),
        ],
        [
            MB("انستجرام 📸 (قريباً)", "soon",    "btn_svc_insta"),
        ],
        [
            MB("⬅️ رجوع", "back_main", "btn_back"),
        ],
    ]
    rows += admin_edit_row("services", uid)
    heading = get_text("services_menu", "🛒 قائمة الخدمات")
    await q.edit_message_text(
        heading,
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML"
    )


async def telegram_services(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    rows = [
        [
            MB("تيليجرام المميز ✅", "premium",        "btn_tg_premium"),
            MB("النجوم ⭐️",          "stars",           "btn_tg_stars"),
        ],
        [
            MB("الرشق 🚀",            "rush_menu",       "btn_tg_rush"),
            MB("نقل أعضاء 🔄",        "transfer",        "btn_tg_transfer"),
        ],
        [
            MB("تعزيزات ⚡️",          "boosts",          "btn_tg_boosts"),
            MB("يوزرات 🆔",            "usernames_shop",  "btn_tg_usernames"),
        ],
        [
            MB("شراء رقم 📲",          "tgl_numbers",     "btn_tg_numbers"),
            MB("💎 مقتنيات رقمية",     "digital_collectibles", "btn_tg_collectibles"),
        ],
        [
            MB("⬅️ رجوع", "services", "btn_back"),
        ],
    ]
    rows += admin_edit_row("tg", uid)
    heading = get_text("telegram_services", "🟦 خدمات تيليجرامية")
    await q.edit_message_text(
        heading,
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML"
    )


async def back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    user = get_user(uid)
    bal  = fmt_bal(user["balance"], user["currency"] or "USD") if user else "0"
    heading = get_text("main_menu", "القائمة الرئيسية 🌹")
    msg     = replace_words_html(f"{heading}\n💰 رصيدك: <b>{bal}</b>")
    await q.edit_message_text(
        msg,
        reply_markup=main_menu(uid),
        parse_mode="HTML"
    )


async def soon(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("قريباً ⏳", show_alert=True)


services_menu_handler     = CallbackQueryHandler(services_menu,     pattern="^services$")
telegram_services_handler = CallbackQueryHandler(
    telegram_services,
    pattern="^telegram_services$"
)
back_main_handler         = CallbackQueryHandler(back_main,         pattern="^back_main$")
soon_handler              = CallbackQueryHandler(soon,              pattern="^soon$")
