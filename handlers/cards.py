"""
شحن بطاقات سوا / لايك كارد + نظام السحب (من رصيد البطاقات فقط)
"""
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters,
)

from config import ADMIN_ID, CURRENCY_SYMBOLS
from db import (
    get_user, get_balance, update_balance, add_balance, is_banned,
    is_card_used, mark_card_used,
    add_pending_card, get_pending_card, update_pending_card,
    get_card_rate, add_daily_usage, get_daily_usage,
    add_risk, get_risk, is_risky, reset_risk,
    convert_from_usd, create_order,
    add_card_loaded, get_card_loaded, get_total_card_balance, deduct_card_balance,
    add_withdrawal, get_withdrawal, update_withdrawal,
    deduct_balance, get_card_history, get_order_group, convert_to_usd,
)
from keyboards import make_btn, admin_edit_row

# ── حالات المحادثة ──────────────────────────────
WAIT_CARD_TYPE  = 50
WAIT_CARD_CODE  = 51
WAIT_WD_COUNTRY = 52
WAIT_WD_METHOD  = 53
WAIT_WD_INFO    = 54
WAIT_WD_AMOUNT  = 55

DAILY_LIMIT_USD = 200.0
_cooldown: dict[int, float] = {}
CARD_AMOUNTS = [17, 20, 25, 50, 100, 200, 300]

WITHDRAW_COUNTRIES = {
    "sa":     "🇸🇦 السعودية",
    "eg":     "🇪🇬 مصر",
    "ye":     "🇾🇪 اليمن",
    "crypto": "💎 عملات رقمية",
}

WITHDRAW_METHODS = {
    "sa":     ["STC Pay", "تحويل بنكي", "محفظة بنكية"],
    "eg":     ["فودافون كاش", "إنستاباي", "محفظة اتصالات", "بنك مصر"],
    "ye":     ["كريمي", "جيب كاش", "وان كاش", "فلوسك"],
    "crypto": ["USDT TRC20", "USDT ERC20", "Bitcoin"],
}

STATUS_LABELS = {
    "pending":  "⏳ قيد المراجعة",
    "approved": "✅ تمت الموافقة",
    "rejected": "❌ مرفوض",
}

TYPE_LABELS = {
    "sawa": "📶 سوا",
    "like": "💳 لايك كارد",
}


async def _notify_orders(bot, text: str, reply_markup=None):
    """إشعار الأدمن + مجموعة الطلبات (إن وُجدت)."""
    await bot.send_message(ADMIN_ID, text, reply_markup=reply_markup, parse_mode="HTML")
    gid = get_order_group()
    if gid:
        try:
            await bot.send_message(gid, text, reply_markup=reply_markup, parse_mode="HTML")
        except Exception:
            pass


def _check_cooldown(uid: int, seconds: float = 5.0) -> bool:
    now = time.time()
    last = _cooldown.get(uid, 0)
    if now - last < seconds:
        return False
    _cooldown[uid] = now
    return True


def _get_user_currency(uid: int) -> tuple[str, str]:
    user = get_user(uid)
    cur = user["currency"] if user else "USD"
    sym = CURRENCY_SYMBOLS.get(cur, cur)
    return cur, sym


def _cards_main_kb(uid: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [
            make_btn("📶 شحن سوا",              "card_type_sawa",  "btn_card_sawa"),
            make_btn("💳 شحن لايك كارد",         "card_type_like",  "btn_card_like"),
        ],
        [make_btn("💸 سحب رصيد البطاقات",        "card_withdraw",   "btn_card_withdraw")],
        [make_btn("📋 سجل الشحن",                "card_history",    "btn_card_history")],
        [make_btn("🔙 رجوع", "main_menu", "btn_cards_back")],
    ]
    rows += admin_edit_row("cards", uid)
    return InlineKeyboardMarkup(rows)


def _admin_card_kb(card_id: int, card_type: str) -> InlineKeyboardMarkup:
    rows = []
    for i in range(0, len(CARD_AMOUNTS), 4):
        rows.append([
            InlineKeyboardButton(str(a), callback_data=f"card_ok_{card_id}_{a}")
            for a in CARD_AMOUNTS[i:i+4]
        ])
    rows.append([
        InlineKeyboardButton("✏️ مبلغ مخصص", callback_data=f"card_custom_{card_id}"),
        InlineKeyboardButton("❌ رفض",        callback_data=f"card_reject_{card_id}"),
    ])
    return InlineKeyboardMarkup(rows)


def _wd_country_kb() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(label, callback_data=f"wd_country_{code}")]
            for code, label in WITHDRAW_COUNTRIES.items()]
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="card_charge")])
    return InlineKeyboardMarkup(rows)


def _wd_method_kb(country_code: str) -> InlineKeyboardMarkup:
    methods = WITHDRAW_METHODS.get(country_code, [])
    rows = [[InlineKeyboardButton(m, callback_data=f"wd_method_{m}")] for m in methods]
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="card_withdraw")])
    return InlineKeyboardMarkup(rows)


# ════════════════════════════════════════════════
# قائمة البطاقات الرئيسية
# ════════════════════════════════════════════════

async def cards_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)
    if is_risky(uid):
        return await q.answer("🚫 حسابك مقيَّد.", show_alert=True)

    ctx.user_data.pop("card", None)
    ctx.user_data.pop("wd", None)

    sawa_usd, like_usd = get_card_loaded(uid)
    cur, sym = _get_user_currency(uid)
    bal      = get_balance(uid)
    bal_loc  = convert_from_usd(bal, cur)

    rate_s   = get_card_rate("sawa")
    rate_l   = get_card_rate("like")
    sawa_sar = (sawa_usd * 100 / rate_s) if rate_s else 0
    like_sar = (like_usd * 100 / rate_l) if rate_l else 0

    total_card_usd = sawa_usd + like_usd
    card_loc       = convert_from_usd(total_card_usd, cur)

    # سطور البطاقات — نُظهرها فقط إن كان فيها رصيد
    sawa_line = f"📶 سوا: <b>{sawa_sar:.0f} ريال</b>  ({convert_from_usd(sawa_usd,cur):.2f} {sym})\n" if sawa_usd > 0 else ""
    like_line = f"💳 لايك كارد: <b>{like_sar:.0f} ريال</b>  ({convert_from_usd(like_usd,cur):.2f} {sym})\n" if like_usd > 0 else ""
    wd_line   = (
        f"💸 متاح للسحب: <b>{card_loc:.2f} {sym}</b>\n"
        if total_card_usd > 0 else ""
    )

    text = (
        "💳 <b>شحن البطاقات</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{sawa_line}"
        f"{like_line}"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 رصيدك الكلي: <b>{bal_loc:.4f} {sym}</b>\n"
        f"{wd_line}"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "اختر من القائمة:"
    )
    await q.edit_message_text(text, reply_markup=_cards_main_kb(uid), parse_mode="HTML")
    return WAIT_CARD_TYPE


async def card_type_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    card_type = "sawa" if q.data == "card_type_sawa" else "like"
    ctx.user_data["card"] = {"type": card_type}
    label = "سوا" if card_type == "sawa" else "لايك كارد"
    await q.edit_message_text(
        f"💳 <b>شحن {label}</b>\n\n"
        f"أرسل كود البطاقة الآن:\n"
        f"<i>ملاحظة: البطاقات بالريال السعودي</i>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data="card_charge"),
        ]]),
        parse_mode="HTML",
    )
    return WAIT_CARD_CODE


async def card_code_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    code = update.message.text.strip()
    data = ctx.user_data.get("card")
    if not data:
        return ConversationHandler.END

    card_type = data["type"]

    # ── التحقق من صيغة كود سوا (14 رقم) ──
    if card_type == "sawa":
        if not (code.isdigit() and len(code) == 14):
            await update.message.reply_text(
                "❌ كود سوا يجب أن يكون 14 رقماً بالضبط.\nأعد إرسال الكود أو اضغط رجوع.",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 رجوع", callback_data="card_charge"),
                ]]),
            )
            return WAIT_CARD_CODE

    if not _check_cooldown(uid, 5.0):
        await update.message.reply_text("⏳ انتظر ثوانٍ قبل إعادة المحاولة.")
        return WAIT_CARD_CODE

    if is_card_used(code):
        pts = add_risk(uid, 40)
        await update.message.reply_text(f"❌ هذا الكود مستخدم مسبقاً.\n⚠️ نقاط الخطورة: {pts}")
        if pts >= 100:
            await update.message.reply_text("🚫 تم تقييد حسابك.")
        return ConversationHandler.END

    if get_daily_usage(uid) >= DAILY_LIMIT_USD:
        add_risk(uid, 10)
        await update.message.reply_text(f"❌ وصلت الحد اليومي ({DAILY_LIMIT_USD:.0f}$).")
        return ConversationHandler.END

    card_id = add_pending_card(uid, card_type, code)
    label   = "سوا" if card_type == "sawa" else "لايك كارد"
    rate    = get_card_rate(card_type)

    # ══ سوا: معالجة تلقائية عبر الطابور ══
    if card_type == "sawa":
        from queue_system import sawa_queue
        from assistant import is_ready as asst_ready

        await sawa_queue.put((uid, code, card_id))

        if asst_ready():
            await update.message.reply_text(
                f"⏳ <b>تم استلام كرت سوا</b>\n\n"
                f"🔄 جاري المعالجة التلقائية…\n"
                f"ستصلك رسالة فور اكتمال العملية.",
                parse_mode="HTML",
            )
        else:
            user_info = update.effective_user
            uname_str = f"@{user_info.username}" if user_info.username else f"ID: {uid}"
            await _notify_orders(
                ctx.bot,
                f"💳 <b>بطاقة سوا جديدة #{card_id}</b>\n"
                f"👤 {uname_str} | <code>{uid}</code>\n"
                f"🔑 الكود: <code>{code}</code>\n"
                f"💱 سعر الصرف: <b>{rate:.1f}</b>\n\n"
                f"اختر المبلغ (بالريال) أو مبلغ مخصص:",
                reply_markup=_admin_card_kb(card_id, card_type),
            )
            await update.message.reply_text(
                f"✅ تم إرسال كرت <b>سوا</b> للمراجعة.\n⏳ سيتم تفعيل رصيدك بعد موافقة الإدارة.",
                parse_mode="HTML",
            )
        ctx.user_data.pop("card", None)
        return ConversationHandler.END

    # ══ لايك كارد: مراجعة يدوية كالمعتاد ══
    await update.message.reply_text(
        f"✅ تم إرسال كرت <b>{label}</b> للمراجعة.\n⏳ سيتم تفعيل رصيدك بعد موافقة الإدارة.",
        parse_mode="HTML",
    )
    user_info = update.effective_user
    uname_str = f"@{user_info.username}" if user_info.username else f"ID: {uid}"
    await _notify_orders(
        ctx.bot,
        f"💳 <b>بطاقة جديدة #{card_id}</b>\n"
        f"👤 {uname_str} | <code>{uid}</code>\n"
        f"📋 النوع: <b>{label}</b>\n"
        f"🔑 الكود: <code>{code}</code>\n"
        f"💱 سعر الصرف: <b>{rate:.1f}</b>\n\n"
        f"اختر المبلغ (بالريال) أو مبلغ مخصص:",
        reply_markup=_admin_card_kb(card_id, card_type),
    )
    ctx.user_data.pop("card", None)
    return ConversationHandler.END


# ════════════════════════════════════════════════
# سجل الشحن
# ════════════════════════════════════════════════

async def card_history_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid     = q.from_user.id
    records = get_card_history(uid, 10)

    if not records:
        await q.edit_message_text(
            "📋 <b>سجل الشحن</b>\n\nلا يوجد سجل بعد.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="card_charge"),
            ]]),
            parse_mode="HTML",
        )
        return WAIT_CARD_TYPE

    cur, sym = _get_user_currency(uid)
    lines = ["📋 <b>آخر 10 عمليات شحن:</b>\n"]
    for row in records:
        rid, card_type, status, amount, created_at, amount_sar = row
        type_lbl   = TYPE_LABELS.get(card_type, card_type)
        status_lbl = STATUS_LABELS.get(status, status)
        date_str   = str(created_at)[:10] if created_at else "—"
        # لسوا نعرض الريال السعودي الأصلي — لغيره نعرض بعملة المستخدم
        if card_type == "sawa" and amount_sar:
            amount_display = f"{amount_sar:.0f} ريال"
        else:
            amount_loc = convert_from_usd(amount, cur) if amount else 0
            amount_display = f"{amount_loc:.2f} {sym}"
        lines.append(
            f"• #{rid} 📶 {type_lbl} | {status_lbl}\n"
            f"  💰 {amount_display} | 📅 {date_str}"
        )

    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data="card_charge"),
        ]]),
        parse_mode="HTML",
    )
    return WAIT_CARD_TYPE


# ════════════════════════════════════════════════
# نظام السحب (من رصيد البطاقات فقط)
# ════════════════════════════════════════════════

async def card_withdraw_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    card_bal = get_total_card_balance(uid)
    if card_bal <= 0:
        return await q.answer(
            "❌ رصيد بطاقاتك صفر. شحن بطاقة أولاً لتتمكن من السحب.",
            show_alert=True
        )

    cur, sym = _get_user_currency(uid)
    card_loc = convert_from_usd(card_bal, cur)
    ctx.user_data["wd"] = {}

    await q.edit_message_text(
        f"💸 <b>سحب رصيد البطاقات</b>\n\n"
        f"💳 رصيد بطاقاتك المتاح للسحب:\n"
        f"<b>{card_loc:.2f} {sym}</b>\n\n"
        f"⚠️ يمكنك السحب من رصيد البطاقات فقط (سوا + لايك كارد)\n\n"
        f"اختر دولتك:",
        reply_markup=_wd_country_kb(),
        parse_mode="HTML",
    )
    return WAIT_WD_COUNTRY


async def wd_country_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    code  = q.data.replace("wd_country_", "")
    label = WITHDRAW_COUNTRIES.get(code, code)
    ctx.user_data.setdefault("wd", {})
    ctx.user_data["wd"]["country_code"]  = code
    ctx.user_data["wd"]["country_label"] = label

    uid = q.from_user.id
    cur, sym = _get_user_currency(uid)
    card_bal = get_total_card_balance(uid)
    card_loc = convert_from_usd(card_bal, cur)

    await q.edit_message_text(
        f"💸 <b>سحب رصيد البطاقات</b>\n"
        f"🌍 الدولة: <b>{label}</b>\n"
        f"💳 رصيدك المتاح: <b>{card_loc:.2f} {sym}</b>\n\n"
        f"اختر نوع المحفظة:",
        reply_markup=_wd_method_kb(code),
        parse_mode="HTML",
    )
    return WAIT_WD_METHOD


async def wd_method_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    method = q.data.replace("wd_method_", "")
    wd = ctx.user_data.get("wd", {})
    wd["method"] = method
    ctx.user_data["wd"] = wd

    uid = q.from_user.id
    cur, sym = _get_user_currency(uid)
    card_bal = get_total_card_balance(uid)
    card_loc = convert_from_usd(card_bal, cur)

    country_label = wd.get("country_label", "")
    await q.edit_message_text(
        f"💸 <b>سحب رصيد البطاقات</b>\n"
        f"🌍 الدولة: <b>{country_label}</b>\n"
        f"💳 المحفظة: <b>{method}</b>\n"
        f"💰 رصيدك المتاح: <b>{card_loc:.2f} {sym}</b>\n\n"
        f"أرسل <b>المبلغ المطلوب سحبه</b> بـ {sym}:\n"
        f"<i>(الحد الأقصى: {card_loc:.2f} {sym})</i>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع", callback_data=f"wd_country_{wd.get('country_code','sa')}"),
        ]]),
        parse_mode="HTML",
    )
    return WAIT_WD_AMOUNT


async def wd_amount_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال المبلغ المطلوب سحبه والتحقق من رصيد البطاقات."""
    uid  = update.effective_user.id
    text = update.message.text.strip().replace(",", ".")
    wd   = ctx.user_data.get("wd", {})

    cur, sym = _get_user_currency(uid)
    card_bal_usd = get_total_card_balance(uid)
    card_loc     = convert_from_usd(card_bal_usd, cur)

    try:
        amount_local = float(text)
        if amount_local <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            f"❌ رقم غير صحيح. أرسل المبلغ بالأرقام فقط (مثال: 50)\n"
            f"💳 رصيدك المتاح: <b>{card_loc:.2f} {sym}</b>",
            parse_mode="HTML",
        )
        return WAIT_WD_AMOUNT

    # تحويل المبلغ المحلي إلى دولار
    amount_usd = convert_to_usd(amount_local, cur)

    if amount_usd > card_bal_usd + 0.0001:
        await update.message.reply_text(
            f"❌ المبلغ يتجاوز رصيد بطاقاتك.\n"
            f"💳 الحد الأقصى: <b>{card_loc:.2f} {sym}</b>",
            parse_mode="HTML",
        )
        return WAIT_WD_AMOUNT

    wd["amount_local"] = amount_local
    wd["amount_usd"]   = amount_usd
    wd["currency"]     = cur
    wd["sym"]          = sym
    ctx.user_data["wd"] = wd

    method        = wd.get("method", "")
    country_label = wd.get("country_label", "")

    await update.message.reply_text(
        f"💸 <b>سحب رصيد البطاقات</b>\n"
        f"🌍 الدولة: <b>{country_label}</b>\n"
        f"💳 المحفظة: <b>{method}</b>\n"
        f"💰 المبلغ: <b>{amount_local:.2f} {sym}</b>\n\n"
        f"أرسل <b>اسمك الكامل ورقم حساب الاستلام</b> في رسالة واحدة\n"
        f"<i>مثال: محمد أحمد — 0501234567</i>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data="card_cancel"),
        ]]),
        parse_mode="HTML",
    )
    return WAIT_WD_INFO


async def wd_info_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    info = update.message.text.strip()
    wd   = ctx.user_data.pop("wd", {})
    if not wd:
        return ConversationHandler.END

    card_bal_usd = get_total_card_balance(uid)
    amount_usd   = wd.get("amount_usd", 0)

    if amount_usd <= 0 or card_bal_usd <= 0:
        await update.message.reply_text("❌ رصيد بطاقاتك غير كافٍ للسحب.")
        return ConversationHandler.END

    country_label = wd.get("country_label", "")
    method        = wd.get("method", "")
    amount_local  = wd.get("amount_local", 0)
    cur           = wd.get("currency", "USD")
    sym           = wd.get("sym", "USD")

    wid = add_withdrawal(uid, country_label, method, info)

    await update.message.reply_text(
        f"✅ <b>تم إرسال طلب السحب #{wid}</b>\n"
        f"💰 المبلغ: <b>{amount_local:.2f} {sym}</b>\n"
        f"⏳ سيتم مراجعته والرد عليك قريباً.",
        parse_mode="HTML",
    )

    user_info = update.effective_user
    uname_str = f"@{user_info.username}" if user_info.username else f"ID: {uid}"
    card_loc  = convert_from_usd(card_bal_usd, cur)

    await _notify_orders(
        ctx.bot,
        f"💸 <b>طلب سحب جديد #{wid}</b>\n"
        f"👤 {uname_str} | <code>{uid}</code>\n"
        f"💳 رصيد بطاقاته: <b>{card_loc:.2f} {sym}</b>\n"
        f"💰 المطلوب: <b>{amount_local:.2f} {sym}</b> ({amount_usd:.4f}$)\n"
        f"🌍 الدولة: <b>{country_label}</b>\n"
        f"💳 المحفظة: <b>{method}</b>\n\n"
        f"📝 معلومات الاستلام:\n<code>{info}</code>",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ قبول السحب", callback_data=f"wd_approve_{wid}"),
                InlineKeyboardButton("❌ رفض",         callback_data=f"wd_reject_{wid}"),
            ]
        ]),
    )
    return ConversationHandler.END


async def cards_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("card", None)
    ctx.user_data.pop("wd", None)
    if update.callback_query:
        await update.callback_query.answer()
        uid = update.callback_query.from_user.id
        # رجوع للقائمة الرئيسية للبطاقات
        sawa_usd, like_usd = get_card_loaded(uid)
        cur, sym = _get_user_currency(uid)
        bal      = get_balance(uid)
        bal_loc  = convert_from_usd(bal, cur)
        rate_s   = get_card_rate("sawa")
        rate_l   = get_card_rate("like")
        sawa_sar = (sawa_usd * 100 / rate_s) if rate_s else 0
        like_sar = (like_usd * 100 / rate_l) if rate_l else 0
        total_card_usd = sawa_usd + like_usd
        total_card_loc = convert_from_usd(total_card_usd, cur)
        text = (
            "💳 <b>شحن البطاقات</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"📶 رصيد سوا المُشحون: <b>{sawa_sar:.0f} ريال</b>\n"
            f"💳 رصيد لايك كارد المُشحون: <b>{like_sar:.0f} ريال</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            f"💸 إجمالي رصيد البطاقات: <b>{total_card_loc:.2f} {sym}</b>\n"
            f"💰 رصيد المحفظة: <b>{bal_loc:.4f} {sym}</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "اختر من القائمة:"
        )
        await update.callback_query.edit_message_text(
            text, reply_markup=_cards_main_kb(uid), parse_mode="HTML"
        )
        return WAIT_CARD_TYPE
    else:
        await update.message.reply_text("❌ تم الإلغاء.")
        return ConversationHandler.END


# ════════════════════════════════════════════════
# الأدمن: قبول / مبلغ مخصص / رفض البطاقة
# ════════════════════════════════════════════════

async def _do_approve_common(ctx, uid, card_id, card_type, code, amount_r):
    rate       = get_card_rate(card_type)
    amount_usd = (amount_r / 100.0) * rate
    label_card = "سوا" if card_type == "sawa" else "لايك كارد"
    add_balance(uid, amount_usd, f"شحن بطاقة {label_card} {amount_r:.0f}ر", "إيداع")
    add_card_loaded(uid, card_type, amount_usd)
    mark_card_used(code, uid)
    update_pending_card(card_id, "approved", amount_usd)
    add_daily_usage(uid, amount_usd)
    create_order(uid, f"card_{card_type}", f"بطاقة {card_type} | {amount_r:.0f}ر", amount_usd)
    label = "سوا" if card_type == "sawa" else "لايك كارد"
    try:
        user = get_user(uid)
        cur, sym = _get_user_currency(uid)
        loc  = convert_from_usd(amount_usd, cur)
        sawa_usd, like_usd = get_card_loaded(uid)
        total_card_loc = convert_from_usd(sawa_usd + like_usd, cur)
        await ctx.bot.send_message(
            uid,
            f"✅ <b>تم شحن رصيد البطاقات</b>\n\n"
            f"📋 بطاقة {label}: <b>{amount_r:.0f} ريال</b>\n"
            f"💰 الرصيد المضاف: <b>{loc:.4f} {sym}</b>\n"
            f"💳 إجمالي رصيد بطاقاتك: <b>{total_card_loc:.2f} {sym}</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    return amount_usd


async def admin_card_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("❌ غير مصرح", show_alert=True)
    await q.answer()
    parts    = q.data.split("_")
    card_id  = int(parts[2])
    amount_r = float(parts[3])
    card     = get_pending_card(card_id)
    if not card:
        return await q.edit_message_text("❌ البطاقة غير موجودة.")
    cid, uid, card_type, code, status, _ = card
    if status != "pending":
        return await q.edit_message_text("⚠️ تمت معالجة هذه البطاقة.")
    amount_usd = await _do_approve_common(ctx, uid, card_id, card_type, code, amount_r)
    await q.edit_message_text(f"✅ تم قبول البطاقة #{card_id}\n💰 {amount_r:.0f}ر → {amount_usd:.4f}$")


async def admin_card_custom_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("❌ غير مصرح", show_alert=True)
    await q.answer()
    card_id = int(q.data.split("_")[2])
    ctx.user_data["custom_card_id"] = card_id
    await q.edit_message_text(
        f"✏️ أدخل المبلغ بالريال للبطاقة #{card_id}:",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data=f"card_reject_{card_id}")
        ]]),
    )


async def admin_card_custom_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    card_id = ctx.user_data.get("custom_card_id")
    if not card_id:
        return
    try:
        amount_r = float(update.message.text.strip())
        if amount_r <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ رقم غير صحيح. أعد الإدخال:")
        return
    ctx.user_data.pop("custom_card_id", None)
    card = get_pending_card(card_id)
    if not card:
        return await update.message.reply_text("❌ البطاقة غير موجودة.")
    cid, uid, card_type, code, status, _ = card
    if status != "pending":
        return await update.message.reply_text("⚠️ تمت معالجة هذه البطاقة.")
    amount_usd = await _do_approve_common(ctx, uid, card_id, card_type, code, amount_r)
    await update.message.reply_text(f"✅ تم قبول البطاقة #{card_id}\n💰 {amount_r:.0f}ر → {amount_usd:.4f}$")


async def admin_card_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("❌ غير مصرح", show_alert=True)
    await q.answer()
    card_id = int(q.data.split("_")[2])
    card    = get_pending_card(card_id)
    if not card:
        return await q.edit_message_text("❌ البطاقة غير موجودة.")
    cid, uid, card_type, code, status, _ = card
    if status != "pending":
        return await q.edit_message_text("⚠️ تمت معالجة هذه البطاقة.")
    update_pending_card(card_id, "rejected", 0)
    label = "سوا" if card_type == "sawa" else "لايك كارد"
    await q.edit_message_text(f"❌ تم رفض بطاقة {label} #{card_id}")
    try:
        await ctx.bot.send_message(
            uid,
            f"❌ <b>تم رفض البطاقة #{card_id}</b>\nتواصل مع الدعم إذا كان هناك خطأ.",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ════════════════════════════════════════════════
# ConversationHandler
# ════════════════════════════════════════════════

cards_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(cards_menu,           pattern="^card_charge$"),
        CallbackQueryHandler(card_withdraw_start,  pattern="^card_withdraw$"),
        CallbackQueryHandler(card_history_cb,      pattern="^card_history$"),
    ],
    states={
        WAIT_CARD_TYPE: [
            CallbackQueryHandler(card_type_selected,  pattern="^card_type_"),
            CallbackQueryHandler(card_withdraw_start,  pattern="^card_withdraw$"),
            CallbackQueryHandler(card_history_cb,      pattern="^card_history$"),
            CallbackQueryHandler(cards_cancel,         pattern="^card_cancel$"),
        ],
        WAIT_CARD_CODE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, card_code_received),
            CallbackQueryHandler(cards_cancel, pattern="^card_charge$"),
            CallbackQueryHandler(cards_cancel, pattern="^card_cancel$"),
        ],
        WAIT_WD_COUNTRY: [
            CallbackQueryHandler(wd_country_selected, pattern="^wd_country_"),
            CallbackQueryHandler(cards_cancel,         pattern="^card_charge$"),
            CallbackQueryHandler(cards_cancel,         pattern="^card_cancel$"),
        ],
        WAIT_WD_METHOD: [
            CallbackQueryHandler(wd_method_selected,  pattern="^wd_method_"),
            CallbackQueryHandler(wd_country_selected, pattern="^wd_country_"),
            CallbackQueryHandler(cards_cancel,         pattern="^card_cancel$"),
        ],
        WAIT_WD_AMOUNT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, wd_amount_received),
            CallbackQueryHandler(wd_country_selected, pattern="^wd_country_"),
            CallbackQueryHandler(cards_cancel,         pattern="^card_cancel$"),
        ],
        WAIT_WD_INFO: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, wd_info_received),
            CallbackQueryHandler(cards_cancel, pattern="^card_cancel$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cards_cancel, pattern="^card_cancel$"),
        CallbackQueryHandler(cards_cancel, pattern="^card_charge$"),
        MessageHandler(filters.COMMAND, cards_cancel),
    ],
    per_message=False,
    allow_reentry=True,
)

admin_card_approve_handler    = CallbackQueryHandler(admin_card_approve,      pattern="^card_ok_")
admin_card_custom_handler     = CallbackQueryHandler(admin_card_custom_start, pattern="^card_custom_")
admin_card_reject_handler     = CallbackQueryHandler(admin_card_reject,       pattern="^card_reject_")
admin_card_custom_msg_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    admin_card_custom_amount,
)
card_history_handler = CallbackQueryHandler(card_history_cb, pattern="^card_history$")
