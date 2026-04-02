"""
باقات سوا STC — عرض مُقسَّم بصفحات (6 باقات/صفحة، عمودين)
الأسعار تظهر بعملة المستخدم | زر رجوع في كل خطوة
"""
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters,
)

from config import ADMIN_ID, CURRENCY_SYMBOLS
from keyboards import make_btn as MB, admin_edit_row
from handlers.direct_pay import set_dp_ctx, insufficient_kb, insufficient_text
from db import (
    get_user, get_balance, deduct_balance, is_banned,
    convert_from_usd, create_order, get_services,
    get_service_by_id, seed_stc_packages,
    add_risk, is_risky, get_order_group,
)

# ── حالات المحادثة ──────────────────────────────
WAIT_STC_PHONE = 40

PAGE_SIZE = 6


async def _notify_orders(bot, text: str, reply_markup=None):
    """إشعار الأدمن + مجموعة الطلبات (إن وُجدت)."""
    await bot.send_message(ADMIN_ID, text, reply_markup=reply_markup, parse_mode="HTML")
    gid = get_order_group()
    if gid:
        try:
            await bot.send_message(gid, text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            pass


def _get_currency(uid: int) -> tuple[str, str]:
    user = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym = CURRENCY_SYMBOLS.get(currency, currency)
    return currency, sym


def _stc_page_kb(page: int, currency: str = "USD", uid: int = 0) -> InlineKeyboardMarkup:
    pkgs  = get_services("stc")
    sym   = CURRENCY_SYMBOLS.get(currency, currency)
    total = len(pkgs)
    start = page * PAGE_SIZE
    end   = min(start + PAGE_SIZE, total)
    slice_ = pkgs[start:end]

    rows = []
    for i in range(0, len(slice_), 2):
        row = []
        for pkg in slice_[i:i+2]:
            sid, name, val, price_usd = pkg
            local = convert_from_usd(price_usd, currency)
            row.append(InlineKeyboardButton(
                f"{name} — {local:.2f} {sym}",
                callback_data=f"stc_buy_{sid}"
            ))
        rows.append(row)

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⏮ السابق", callback_data=f"stc_page_{page-1}"))
    if end < total:
        nav.append(InlineKeyboardButton("⏭ التالي", callback_data=f"stc_page_{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([MB("🔙 رجوع", "general", "btn_back")])
    rows += admin_edit_row("stc_sec", uid)
    return InlineKeyboardMarkup(rows)


async def stc_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض أول صفحة من الباقات"""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)
    seed_stc_packages()
    ctx.user_data.pop("stc", None)
    currency, sym = _get_currency(uid)
    bal = get_balance(uid)
    bal_loc = convert_from_usd(bal, currency)
    await q.edit_message_text(
        f"📶 <b>باقات سوا STC</b>\n"
        f"💰 رصيدك: <b>{bal_loc:.2f} {sym}</b>\n\n"
        f"اختر الباقة المناسبة:",
        reply_markup=_stc_page_kb(0, currency, uid),
        parse_mode="HTML",
    )


async def stc_page(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تنقل بين الصفحات"""
    q = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    page = int(q.data.split("_")[2])
    currency, sym = _get_currency(uid)
    bal = get_balance(uid)
    bal_loc = convert_from_usd(bal, currency)
    await q.edit_message_text(
        f"📶 <b>باقات سوا STC</b>\n"
        f"💰 رصيدك: <b>{bal_loc:.2f} {sym}</b>\n\n"
        f"اختر الباقة المناسبة:",
        reply_markup=_stc_page_kb(page, currency, uid),
        parse_mode="HTML",
    )


async def stc_buy_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 1: اختار الباقة → اطلب رقم الهاتف"""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if is_risky(uid):
        return await q.answer("🚫 حسابك مقيَّد مؤقتاً. تواصل مع الدعم.", show_alert=True)

    sid = int(q.data.split("_")[2])
    pkg = get_service_by_id(sid)
    if not pkg:
        return await q.answer("❌ الباقة غير موجودة", show_alert=True)

    _, cat, name, val, price_usd = pkg
    currency, sym = _get_currency(uid)
    local = convert_from_usd(price_usd, currency)

    bal = get_balance(uid)
    if bal < price_usd:
        set_dp_ctx(ctx, svc="stc", label=f"باقة STC: {name}", usd=price_usd, back_cb="stc_back")
        await q.answer()
        await q.edit_message_text(
            insufficient_text(bal, price_usd, currency, sym),
            parse_mode="HTML",
            reply_markup=insufficient_kb("stc_back"),
        )
        return WAIT_STC_PHONE

    ctx.user_data["stc"] = {"sid": sid, "name": name, "price_usd": price_usd, "currency": currency}

    await q.edit_message_text(
        f"📶 <b>{name}</b>\n"
        f"💰 السعر: <b>{local:.2f} {sym}</b>\n\n"
        f"📱 أرسل رقم الهاتف (05xxxxxxxx):",
        reply_markup=InlineKeyboardMarkup([[
            MB("🔙 رجوع لقائمة STC", "stc_back", "btn_stc_back"),
        ]]),
        parse_mode="HTML",
    )
    return WAIT_STC_PHONE


async def stc_receive_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: استقبال رقم الهاتف → شاشة التأكيد"""
    uid   = update.effective_user.id
    phone = update.message.text.strip()
    data  = ctx.user_data.get("stc")

    if not data:
        return ConversationHandler.END

    if not (phone.isdigit() and phone.startswith("05") and len(phone) == 10):
        await update.message.reply_text(
            "❌ رقم غير صحيح. أرسل رقماً يبدأ بـ 05 ومؤلف من 10 أرقام:",
            reply_markup=InlineKeyboardMarkup([[
                MB("🔙 رجوع لقائمة STC", "stc_back", "btn_stc_back"),
            ]]),
        )
        add_risk(uid, 5)
        return WAIT_STC_PHONE

    currency = data.get("currency", "USD")
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    local    = convert_from_usd(data["price_usd"], currency)

    ctx.user_data["stc"]["phone"] = phone

    await update.message.reply_text(
        f"⚠️ <b>تأكيد الطلب</b>\n\n"
        f"📶 <b>{data['name']}</b>\n"
        f"📱 <b>{phone}</b>\n"
        f"💰 <b>{local:.2f} {sym}</b>\n\n"
        f"هل تريد المتابعة؟",
        reply_markup=InlineKeyboardMarkup([
            [
                MB("✅ تأكيد",         "stc_confirm", "btn_stc_confirm"),
                MB("🔙 رجوع",          "stc_back",    "btn_back"),
            ]
        ]),
        parse_mode="HTML",
    )
    return WAIT_STC_PHONE


async def stc_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 3: تأكيد — اقتطاع الرصيد وإشعار الأدمن"""
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    data = ctx.user_data.get("stc")
    if not data or "phone" not in data:
        await q.edit_message_text("❌ انتهت الجلسة، اختر الباقة من جديد.")
        return ConversationHandler.END

    price_usd = data["price_usd"]
    bal       = get_balance(uid)

    if bal < price_usd:
        currency, sym = _get_currency(uid)
        set_dp_ctx(ctx, svc="stc", label=f"باقة STC: {data['name']}", usd=price_usd, back_cb="stc_back")
        await q.edit_message_text(
            insufficient_text(bal, price_usd, currency, sym),
            parse_mode="HTML",
            reply_markup=insufficient_kb("stc_back"),
        )
        ctx.user_data.pop("stc", None)
        return ConversationHandler.END

    deduct_balance(uid, price_usd, f"شراء: باقة STC {data.get('name', '')}")
    oid = create_order(uid, "stc", f"{data['name']} | {data['phone']}", price_usd)

    currency, sym = _get_currency(uid)
    local = convert_from_usd(price_usd, currency)

    await q.edit_message_text(
        f"✅ <b>تم استقبال طلبك</b>\n\n"
        f"📶 {data['name']}\n"
        f"📱 {data['phone']}\n"
        f"💰 {local:.2f} {sym}\n\n"
        f"⏳ سيتم التنفيذ قريباً.",
        parse_mode="HTML",
    )

    user_info = q.from_user
    uname_str = f"@{user_info.username}" if user_info.username else f"ID: {uid}"
    await _notify_orders(
        ctx.bot,
        f"📶 <b>طلب STC #{oid}</b>\n"
        f"👤 {uname_str} | <code>{uid}</code>\n"
        f"📦 {data['name']}\n"
        f"📱 {data['phone']}\n"
        f"💲 {price_usd:.2f}$",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏳ جارٍ المعالجة", callback_data=f"process_{oid}")],
            [
                InlineKeyboardButton("✅ تم",    callback_data=f"done_{oid}"),
                InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{oid}"),
            ],
        ]),
    )

    ctx.user_data.pop("stc", None)
    return ConversationHandler.END


async def stc_back(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الرجوع لقائمة STC دون إنهاء البوت."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    ctx.user_data.pop("stc", None)
    seed_stc_packages()
    currency, sym = _get_currency(uid)
    bal = get_balance(uid)
    bal_loc = convert_from_usd(bal, currency)
    await q.edit_message_text(
        f"📶 <b>باقات سوا STC</b>\n"
        f"💰 رصيدك: <b>{bal_loc:.2f} {sym}</b>\n\n"
        f"اختر الباقة المناسبة:",
        reply_markup=_stc_page_kb(0, currency, uid),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ── تجميع الـ handlers ───────────────────────────

stc_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(stc_buy_select, pattern="^stc_buy_")],
    states={
        WAIT_STC_PHONE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, stc_receive_phone),
            CallbackQueryHandler(stc_confirm, pattern="^stc_confirm$"),
            CallbackQueryHandler(stc_back,    pattern="^stc_back$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(stc_back, pattern="^stc_back$"),
        MessageHandler(filters.COMMAND, stc_back),
    ],
    per_message=False,
    allow_reentry=True,
)

stc_menu_handler = CallbackQueryHandler(stc_menu, pattern="^stc_menu$")
stc_page_handler = CallbackQueryHandler(stc_page, pattern="^stc_page_")
stc_back_handler = CallbackQueryHandler(stc_back, pattern="^stc_back$")
