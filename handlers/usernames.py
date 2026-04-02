"""
متجر اليوزرات 🆔 — متجر روز
نظام شراء احترافي: عرض → حجز مؤقت (90 ث) → تأكيد → خصم → تسليم
نوعان: ملكية (نقل مباشر) | منصة (إرسال محفظة)
"""

import asyncio
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

from config import CURRENCY_SYMBOLS, ADMIN_ID
from keyboards import make_btn as MB, admin_edit_row
from db import (
    get_user, get_balance, deduct_balance, is_banned,
    convert_from_usd, create_order,
    get_available_usernames, get_username_by_id,
    reserve_username, release_username, mark_username_sold,
)

log = logging.getLogger(__name__)

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — —"

WAIT_WALLET = 30   # حالة انتظار المحفظة

TYPE_ICONS = {
    "ملكية":  "👑",
    "قناة":   "📢",
    "منصة":   "💼",
    "بوت":    "🤖",
}


# ─────────────────────────────────────────────────────
# مساعدات
# ─────────────────────────────────────────────────────

def _icon(t: str) -> str:
    return TYPE_ICONS.get(t, "🆔")


async def _edit(q, text: str, kb=None):
    try:
        await q.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


def _back_kb():
    return InlineKeyboardMarkup([[
        MB("⬅️ رجوع", "usernames_shop", "btn_back")
    ]])


# ─────────────────────────────────────────────────────
# 1. القائمة الرئيسية — عرض اليوزرات المتاحة
# ─────────────────────────────────────────────────────

async def usernames_shop_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    rows     = get_available_usernames()
    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    if not rows:
        empty_rows = [
            [
                MB("🛟 الدعم", "support",           "btn_support_nav"),
                MB("⬅️ رجوع", "telegram_services",  "btn_back"),
            ]
        ]
        empty_rows += admin_edit_row("usernames_sec", uid)
        await _edit(q,
            f"{SEP}\n🆔 متجر اليوزرات\n{SEP}\n\n"
            "لا يوجد يوزرات متاحة حالياً.\n"
            "تواصل مع الدعم لمعرفة القادم قريباً 👀",
            InlineKeyboardMarkup(empty_rows)
        )
        return

    kb_rows = []
    for r in rows:
        price_usd = r["price"]
        price_loc = convert_from_usd(price_usd, currency)
        icon      = _icon(r["type"])
        label     = f"{icon} @{r['username']}  [{r['type']}]  — {price_loc:.2f} {sym}"
        kb_rows.append([InlineKeyboardButton(label, callback_data=f"uname_buy_{r['id']}")])

    kb_rows.append([MB("⬅️ رجوع", "telegram_services", "btn_back")])
    kb_rows += admin_edit_row("usernames_sec", uid)

    await _edit(q,
        f"{SEP}\n🆔 متجر اليوزرات\n{SEP}\n\n"
        f"<b>{len(rows)}</b> يوزر متاح — اختر لعرض التفاصيل:\n\n"
        "👑 ملكية = نقل ملكية كامل للحساب\n"
        "📢 قناة = نقل ملكية القناة\n"
        "💼 منصة = إرسال عبر محفظة تيليجرام",
        InlineKeyboardMarkup(kb_rows)
    )


# ─────────────────────────────────────────────────────
# 2. تفاصيل اليوزر المختار — حجز مؤقت
# ─────────────────────────────────────────────────────

async def uname_buy_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    row_id    = int(q.data.replace("uname_buy_", ""))
    row       = get_username_by_id(row_id)

    if not row or row["status"] != "available":
        await _edit(q,
            f"{SEP}\n⚠️ اليوزر غير متاح\n{SEP}\n\n"
            "تم حجزه مؤخراً. جرّب يوزراً آخر.",
            _back_kb()
        )
        return

    # حجز مؤقت 90 ثانية
    if not reserve_username(row_id, uid, seconds=90):
        await _edit(q,
            f"{SEP}\n⚠️ اليوزر غير متاح\n{SEP}\n\nتم حجزه للتو.",
            _back_kb()
        )
        return

    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    balance  = get_balance(uid)

    price_usd = row["price"]
    price_loc = convert_from_usd(price_usd, currency)
    bal_loc   = convert_from_usd(balance,   currency)
    icon      = _icon(row["type"])

    sufficient = balance >= price_usd

    ctx.user_data["uname_order"] = {
        "row_id":    row_id,
        "username":  row["username"],
        "type":      row["type"],
        "price_usd": price_usd,
    }

    # زر التأكيد
    if sufficient:
        kb = InlineKeyboardMarkup([
            [MB("✅ تأكيد الشراء", "uname_confirm", "btn_uname_confirm")],
            [MB("❌ إلغاء",         "uname_cancel",  "btn_cancel")],
        ])
        msg = (
            f"{SEP}\n{icon} @{row['username']}\n{SEP2}\n"
            f"📦 النوع:   <b>{row['type']}</b>\n"
            f"💲 السعر:  <b>{price_loc:.2f} {sym}</b>\n"
            f"💰 رصيدك: <b>{bal_loc:.2f} {sym}</b>\n\n"
            "⏳ <i>الحجز ينتهي بعد 90 ثانية</i>\n\n"
            "هل تريد إتمام الشراء؟"
        )
    else:
        # رصيد غير كافٍ — نفك الحجز فوراً
        release_username(row_id)
        ctx.user_data.pop("uname_order", None)
        kb = InlineKeyboardMarkup([
            [MB("💳 شحن الرصيد", "deposit",        "btn_charge")],
            [MB("⬅️ رجوع",       "usernames_shop", "btn_back")],
        ])
        msg = (
            f"{SEP}\n❌ رصيد غير كافٍ\n{SEP2}\n"
            f"💲 السعر:  <b>{price_loc:.2f} {sym}</b>\n"
            f"💰 رصيدك: <b>{bal_loc:.2f} {sym}</b>\n\n"
            f"تحتاج <b>{convert_from_usd(price_usd-balance, currency):.2f} {sym}</b> إضافية."
        )

    await _edit(q, msg, kb)

    # مؤقت تلقائي لفك الحجز بعد 90 ثانية
    if sufficient:
        asyncio.get_event_loop().call_later(
            91,
            lambda: asyncio.ensure_future(_auto_release(row_id, uid))
        )


async def _auto_release(row_id: int, uid: int):
    """يفك الحجز تلقائياً إذا انقضى الوقت."""
    row = get_username_by_id(row_id)
    if row and row["status"] == "reserved" and row["reserved_by"] == uid:
        release_username(row_id)
        log.info("Auto-released username id=%s for uid=%s", row_id, uid)


# ─────────────────────────────────────────────────────
# 3. تأكيد الشراء
# ─────────────────────────────────────────────────────

async def uname_confirm_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    order = ctx.user_data.get("uname_order")
    if not order:
        await _edit(q, "⚠️ انتهت جلسة الشراء.", _back_kb())
        return

    row_id    = order["row_id"]
    row       = get_username_by_id(row_id)

    if not row or row["status"] not in ("available", "reserved"):
        ctx.user_data.pop("uname_order", None)
        await _edit(q,
            f"{SEP}\n⚠️ اليوزر لم يعد متاحاً\n{SEP}\nتم بيعه للتو.",
            _back_kb()
        )
        return

    price_usd = order["price_usd"]
    balance   = get_balance(uid)

    if balance < price_usd:
        release_username(row_id)
        ctx.user_data.pop("uname_order", None)
        user     = get_user(uid)
        currency = user["currency"] if user else "USD"
        sym      = CURRENCY_SYMBOLS.get(currency, currency)
        await _edit(q,
            f"{SEP}\n❌ رصيد غير كافٍ\n{SEP}\n"
            f"رصيدك: {convert_from_usd(balance,currency):.2f} {sym}",
            InlineKeyboardMarkup([[
                InlineKeyboardButton("💳 شحن الرصيد", callback_data="deposit"),
                InlineKeyboardButton("⬅️ رجوع",       callback_data="usernames_shop"),
            ]])
        )
        return

    # خصم الرصيد
    deduct_balance(uid, price_usd, f"شراء: يوزر @{order.get('username', '')}")
    mark_username_sold(row_id)
    create_order(uid, "username_shop", f"@{order['username']} [{order['type']}]", price_usd)
    ctx.user_data.pop("uname_order", None)

    uname = order["username"]
    utype = order["type"]
    icon  = _icon(utype)

    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    # تسليم حسب النوع
    if utype in ("ملكية", "قناة"):
        # ملكية مباشرة — يُطلب منه الانضمام للقناة
        await _edit(q,
            f"{SEP}\n✅ تم الشراء بنجاح!\n{SEP2}\n\n"
            f"{icon} اليوزر: <code>@{uname}</code>\n"
            f"📦 النوع: <b>{utype}</b>\n"
            f"💲 المدفوع: <b>{convert_from_usd(price_usd,currency):.2f} {sym}</b>\n\n"
            "📌 <b>خطوة التسليم:</b>\n"
            f"انضم للقناة للإتمام:\n"
            f"👉 <a href='https://t.me/{uname}'>t.me/{uname}</a>\n\n"
            "إذا واجهت مشكلة تواصل مع الدعم 🛟",
            InlineKeyboardMarkup([
                [InlineKeyboardButton(f"🔗 t.me/{uname}", url=f"https://t.me/{uname}")],
                [MB("🛟 الدعم",  "support",   "btn_support_nav"),
                 MB("⬅️ القائمة", "main_menu", "btn_back_main")],
            ])
        )
        # إشعار الأدمن
        await _notify_admin(ctx, uid, uname, utype, price_usd)

    else:
        # منصة/بوت — يطلب منه المحفظة
        ctx.user_data["uname_wallet_order"] = {
            "username": uname,
            "type":     utype,
            "price":    price_usd,
        }
        await _edit(q,
            f"{SEP}\n✅ تم الدفع — أرسل محفظتك\n{SEP2}\n\n"
            f"{icon} اليوزر: <code>@{uname}</code>\n\n"
            "📩 أرسل عنوان محفظة تيليجرام (TON Wallet) لإتمام التسليم:",
            InlineKeyboardMarkup([[
                MB("❌ إلغاء", "uname_wallet_cancel", "btn_cancel")
            ]])
        )
        return WAIT_WALLET


# ─────────────────────────────────────────────────────
# 4. استقبال المحفظة (للنوع: منصة/بوت)
# ─────────────────────────────────────────────────────

async def uname_wallet_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    wallet  = update.message.text.strip()
    order   = ctx.user_data.get("uname_wallet_order", {})

    if not order:
        return ConversationHandler.END

    uname = order.get("username", "")
    utype = order.get("type", "")
    price = order.get("price", 0)

    if len(wallet) < 10:
        await update.message.reply_text(
            "❌ عنوان المحفظة قصير جداً. أرسل عنواناً صحيحاً:",
        )
        return WAIT_WALLET

    ctx.user_data.pop("uname_wallet_order", None)

    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    await update.message.reply_text(
        f"{SEP}\n✅ تم استلام المحفظة\n{SEP2}\n\n"
        f"🆔 اليوزر: <code>@{uname}</code>\n"
        f"💼 المحفظة: <code>{wallet}</code>\n\n"
        "⏳ جاري التسليم من قِبل الفريق…",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            MB("⬅️ القائمة الرئيسية", "main_menu", "btn_back_main")
        ]])
    )

    # إشعار الأدمن مع المحفظة
    await _notify_admin(ctx, uid, uname, utype, price, wallet=wallet)
    return ConversationHandler.END


# ─────────────────────────────────────────────────────
# 5. إلغاء
# ─────────────────────────────────────────────────────

async def uname_cancel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    order = ctx.user_data.pop("uname_order", None)
    if order:
        release_username(order["row_id"])

    await _edit(q,
        "❌ تم الإلغاء — تم فك الحجز.",
        InlineKeyboardMarkup([[
            MB("⬅️ متجر اليوزرات", "usernames_shop", "btn_back")
        ]])
    )
    return ConversationHandler.END


async def uname_wallet_cancel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data.pop("uname_wallet_order", None)
    await _edit(q,
        "⚠️ تم الدفع ولكن لم يتم إرسال المحفظة.\n"
        "تواصل مع الدعم لاسترداد اليوزر.",
        InlineKeyboardMarkup([[
            MB("🛟 الدعم",  "support",   "btn_support_nav"),
            MB("⬅️ القائمة", "main_menu", "btn_back_main"),
        ]])
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────────────
# إشعار الأدمن
# ─────────────────────────────────────────────────────

async def _notify_admin(ctx, uid: int, uname: str, utype: str, price: float, wallet: str = ""):
    user   = get_user(uid)
    u_name = f"@{user['username']}" if user and user["username"] else str(uid)
    icon   = _icon(utype)
    text   = (
        f"🛍 طلب يوزر جديد\n\n"
        f"👤 المشتري: {u_name} (<code>{uid}</code>)\n"
        f"{icon} اليوزر: @{uname}\n"
        f"📦 النوع: {utype}\n"
        f"💲 السعر: {price}$"
    )
    if wallet:
        text += f"\n💼 المحفظة: <code>{wallet}</code>"
    try:
        await ctx.bot.send_message(ADMIN_ID, text, parse_mode="HTML")
    except Exception:
        pass


# ─────────────────────────────────────────────────────
# تسجيل الـ Handlers
# ─────────────────────────────────────────────────────

usernames_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(uname_buy_cb, pattern=r"^uname_buy_\d+$"),
    ],
    states={
        WAIT_WALLET: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, uname_wallet_msg),
            CallbackQueryHandler(uname_wallet_cancel_cb, pattern="^uname_wallet_cancel$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(uname_cancel_cb, pattern="^uname_cancel$"),
    ],
    allow_reentry=True,
    name="uname_conv",
)

usernames_shop_handler  = CallbackQueryHandler(usernames_shop_menu, pattern="^usernames_shop$")
uname_confirm_handler   = CallbackQueryHandler(uname_confirm_cb,    pattern="^uname_confirm$")
uname_cancel_handler    = CallbackQueryHandler(uname_cancel_cb,     pattern="^uname_cancel$")
