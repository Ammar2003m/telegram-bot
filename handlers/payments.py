from pdf_gen import generate_statement_pdf
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, PreCheckoutQueryHandler,
    ConversationHandler, ContextTypes, filters
)

from config import ADMIN_ID, CURRENCY_SYMBOLS
from db import (get_user, update_balance, add_balance, get_balance, convert_to_usd,
                get_referrer, get_ref_percent,
                is_invoice_processed, mark_invoice_processed,
                get_price)
from keyboards import back, make_btn as MB, make_styled_btn as SB, admin_edit_row
import cryptopay as CP

SEP  = "━━━━━━━━━━━━━━━"
SEP2 = "───────────────"

# ── حالات المحادثة ─────────────────────────────────
DEP_AMOUNT  = 0   # شاشة اختيار/إدخال المبلغ
DEP_CUSTOM  = 1   # إدخال مبلغ مخصص (نص)
DEP_METHOD  = 2   # اختيار طريقة الدفع
DEP_RECEIPT = 3   # إرسال صورة الإيصال

# ── مبالغ مقترحة لكل دولة (قابلة للتعديل) ──────────
PRESET_AMOUNTS = {
    "yemen":  [1_000, 2_000, 5_000, 10_000, 20_000],
    "ksa":    [10,    25,    50,    100,    200],
    "egypt":  [50,    100,   200,   500,    1_000],
    "crypto": [5,     10,    25,    50,     100],
}

# ── بيانات طرق الدفع التفصيلية ─────────────────────
PAYMENTS = {
    "yemen": {
        "kurimi": {
            "name":    "🏦 بنك الكريمي",
            "btn_key": "btn_dep_kurimi",
            "text": (
                "بنك الكريمي — دفع مشتريات\n"
                "اسم النقطة: <b>Store Roz</b>\n"
                "رقم النقطة: <code>1535484</code>"
            ),
        },
        "jeeb": {
            "name":    "📱 محفظة جيب",
            "btn_key": "btn_dep_jeeb",
            "text": "رقم الحساب: <code>123828</code>",
        },
        "onecash": {
            "name":    "💚 ون كاش",
            "btn_key": "btn_dep_onecash",
            "text": "رقم الحساب: <code>158617033</code>",
        },
        "floosak": {
            "name":    "📲 جوالي / فلوسك",
            "btn_key": "btn_dep_floosak",
            "text": "رقم الحساب: <code>773072166</code>",
        },
        "name_transfer": {
            "name":    "🔄 تحويل عبر الاسم",
            "btn_key": "btn_dep_nametrans",
            "text": (
                "الاسم: <b>عبدالملك جلال محمد احمد الشامي</b>\n"
                "رقم الهاتف: <code>773072166</code>\n"
                "⚠️ يرجى عدم التحويل عبر شبكة دادية"
            ),
        },
    },
    "ksa": {
        "alarabi": {
            "name":    "🏦 بنك العربي",
            "btn_key": "btn_dep_alarabi",
            "text": (
                "رقم الآيبان: <code>SA0430400108038585440011</code>\n"
                "الاسم: <b>احمد حافظ</b>"
            ),
        },
        "alinma": {
            "name":    "🏦 بنك الإنماء",
            "btn_key": "btn_dep_alinma",
            "text": (
                "رقم الآيبان: <code>SA9305000068206294433000</code>\n"
                "الاسم: <b>احمد حافظ</b>"
            ),
        },
    },
    "egypt": {
        "vodafone": {
            "name":    "📱 فودافون كاش",
            "btn_key": "btn_dep_vodafone",
            "text": "رقم الحساب: <code>01017327583</code>",
        },
    },
    "crypto": {
        "binance": {
            "name":    "🟡 Binance ID",
            "btn_key": "btn_dep_binance",
            "text": "Binance ID: <code>1050439146</code>",
        },
        "cryptopay": {
            "name":      "🤖 CryptoPay (تلقائي ✅)",
            "btn_key":   "btn_dep_cryptopay",
            "cryptopay": "USDT",
        },
    },
}

COUNTRY_LABEL = {
    "yemen":  "ريال يمني 🇾🇪",
    "ksa":    "ريال سعودي 🇸🇦",
    "egypt":  "جنيه مصري 🇪🇬",
    "crypto": "USDT 💲",
}

COUNTRY_FLAG = {
    "yemen":  "🇾🇪",
    "ksa":    "🇸🇦",
    "egypt":  "🇪🇬",
    "crypto": "💲",
}

COUNTRY_CURRENCY = {
    "yemen":  "YER",
    "ksa":    "SAR",
    "egypt":  "EGP",
    "crypto": "USD",
}


# ── دوال بناء لوحات المفاتيح ──────────────────────

def _amounts_kb(country: str) -> InlineKeyboardMarkup:
    """لوحة مفاتيح اختيار المبلغ (المقترحات + مخصص + رجوع)."""
    label   = COUNTRY_LABEL.get(country, "")
    presets = PRESET_AMOUNTS.get(country, [])
    rows    = []
    # صفوف من زرّين
    pair = []
    for amt in presets:
        disp = f"{amt:,} {label.split()[0]}"          # مثال: 1,000 ريال
        pair.append(SB(disp, f"dep_amt_{country}_{amt}", "btn_dep_custom"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    # زر المبلغ المخصص
    rows.append([MB("✏️ مبلغ مخصص", f"dep_custom_{country}", "btn_dep_custom")])
    rows.append([MB("⬅️ رجوع", "deposit", "btn_back")])
    return InlineKeyboardMarkup(rows)


def _methods_kb(country: str) -> InlineKeyboardMarkup:
    """لوحة مفاتيح اختيار طريقة الدفع."""
    methods = PAYMENTS.get(country, {})
    rows = [
        [MB(info["name"], f"dep_method_{country}_{key}", info["btn_key"])]
        for key, info in methods.items()
    ]
    rows.append([MB("⬅️ رجوع", f"dep_country_{country}", "btn_back")])
    return InlineKeyboardMarkup(rows)


# ══════════════════════════════════════════════════════
# 1. قائمة الدول
# ══════════════════════════════════════════════════════

async def deposit_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    rows = [
        [
            MB("🇾🇪 اليمن",          "dep_country_yemen",  "btn_dep_yemen"),
            MB("🇸🇦 السعودية",       "dep_country_ksa",    "btn_dep_saudi"),
        ],
        [
            MB("🇪🇬 مصر",            "dep_country_egypt",  "btn_dep_egypt"),
            MB("💲 عملات رقمية",     "dep_country_crypto", "btn_dep_crypto"),
        ],
        [
            MB("⭐ نجوم تيليجرام",   "dep_stars_menu",     "btn_dep_stars"),
        ],
        [
            MB("⬅️ رجوع", "back_main", "btn_back"),
        ],
    ]
    rows += admin_edit_row("deposit", uid)
    await q.edit_message_text(
        f"{SEP}\n💳 شحن الرصيد\n{SEP}\n\nاختر طريقة الشحن:",
        reply_markup=InlineKeyboardMarkup(rows)
    )


# ══════════════════════════════════════════════════════
# 2. عرض المبالغ المقترحة (نقطة دخول المحادثة)
# ══════════════════════════════════════════════════════

async def show_amounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    country = q.data.replace("dep_country_", "")
    ctx.user_data["dep"] = {
        "country":  country,
        "currency": COUNTRY_CURRENCY.get(country, "USD"),
    }
    # حفظ بيانات الرسالة للتعديل لاحقاً عند إدخال نص
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id,
                                "msg_id":  q.message.message_id}

    flag  = COUNTRY_FLAG.get(country, "🌐")
    label = COUNTRY_LABEL.get(country, country)
    await q.edit_message_text(
        f"{SEP}\n{flag} اختر المبلغ — {label}\n{SEP}\n\n"
        f"اختر مبلغاً جاهزاً أو اكتب مبلغاً مخصصاً:",
        reply_markup=_amounts_kb(country)
    )
    return DEP_AMOUNT


# ══════════════════════════════════════════════════════
# 3أ. اختيار مبلغ جاهز → عرض طرق الدفع
# ══════════════════════════════════════════════════════

async def select_preset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    # dep_amt_{country}_{amount}
    raw     = q.data[len("dep_amt_"):]           # country_amount
    country, amt_str = raw.split("_", 1)
    amount  = float(amt_str)
    currency = COUNTRY_CURRENCY.get(country, "USD")
    usd      = convert_to_usd(amount, currency)

    ctx.user_data["dep"] = {
        "country":  country,
        "currency": currency,
        "amount":   amount,
        "amount_usd": usd,
    }
    label = COUNTRY_LABEL.get(country, "")
    flag  = COUNTRY_FLAG.get(country, "🌐")

    await q.edit_message_text(
        f"{SEP}\n{flag} اختر طريقة الدفع\n{SEP}\n\n"
        f"💰 المبلغ: <b>{amount:,.0f} {label}</b>\n"
        f"≈ <b>{usd:.4f}$</b>\n\n"
        f"اختر طريقة الدفع:",
        parse_mode="HTML",
        reply_markup=_methods_kb(country)
    )
    return DEP_METHOD


# ══════════════════════════════════════════════════════
# 3ب. مبلغ مخصص → طلب إدخال النص
# ══════════════════════════════════════════════════════

async def ask_custom(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    country = q.data.replace("dep_custom_", "")
    dep     = ctx.user_data.get("dep", {})
    dep["country"]  = country
    dep["currency"] = COUNTRY_CURRENCY.get(country, "USD")
    ctx.user_data["dep"] = dep

    label = COUNTRY_LABEL.get(country, "")
    flag  = COUNTRY_FLAG.get(country, "🌐")
    await q.edit_message_text(
        f"{SEP}\n{flag} مبلغ مخصص\n{SEP}\n\n"
        f"أرسل المبلغ الذي تريد شحنه بـ <b>{label}</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [MB("⬅️ رجوع", f"dep_country_{country}", "btn_back")]
        ])
    )
    return DEP_CUSTOM


# ══════════════════════════════════════════════════════
# 3ج. استقبال المبلغ المخصص → عرض طرق الدفع
# ══════════════════════════════════════════════════════

async def recv_custom_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(update.message.text.strip().replace(",", ""))
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقماً صحيحاً أكبر من صفر.")
        return DEP_CUSTOM

    dep      = ctx.user_data.get("dep", {})
    country  = dep.get("country", "crypto")
    currency = dep.get("currency", "USD")
    usd      = convert_to_usd(amount, currency)
    dep["amount"]     = amount
    dep["amount_usd"] = usd
    ctx.user_data["dep"] = dep

    label = COUNTRY_LABEL.get(country, "")
    flag  = COUNTRY_FLAG.get(country, "🌐")

    # حذف رسالة المستخدم وتعديل رسالة البوت
    try:
        await update.message.delete()
    except Exception:
        pass

    bm = ctx.user_data.get("bot_msg", {})
    text = (
        f"{SEP}\n{flag} اختر طريقة الدفع\n{SEP}\n\n"
        f"💰 المبلغ: <b>{amount:,.2f} {label}</b>\n"
        f"≈ <b>{usd:.4f}$</b>\n\n"
        f"اختر طريقة الدفع:"
    )
    kb = _methods_kb(country)
    if bm:
        try:
            await ctx.bot.edit_message_text(
                chat_id=bm["chat_id"],
                message_id=bm["msg_id"],
                text=text,
                parse_mode="HTML",
                reply_markup=kb
            )
            return DEP_METHOD
        except Exception:
            pass
    await update.effective_chat.send_message(text, parse_mode="HTML", reply_markup=kb)
    return DEP_METHOD


# ══════════════════════════════════════════════════════
# 4. اختيار طريقة الدفع → عرض التفاصيل + طلب الإيصال
#    أو إنشاء فاتورة CryptoPay تلقائية
# ══════════════════════════════════════════════════════

async def show_details(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    # dep_method_{country}_{key}   (key قد يحتوي _)
    raw     = q.data[len("dep_method_"):]
    country, key = raw.split("_", 1)

    info    = PAYMENTS[country][key]
    dep     = ctx.user_data.get("dep", {})
    amount  = dep.get("amount", 0)
    usd     = dep.get("amount_usd", 0)
    label   = COUNTRY_LABEL.get(country, "")
    flag    = COUNTRY_FLAG.get(country, "🌐")
    uid     = q.from_user.id

    dep["method"]  = info["name"]
    dep["country"] = country
    ctx.user_data["dep"] = dep

    # ── مسار CryptoPay (تلقائي) ─────────────────────
    if info.get("cryptopay"):
        asset  = info["cryptopay"]
        result = await CP.create_invoice(uid, usd, asset=asset)

        if not result:
            await q.edit_message_text(
                f"{SEP}\n❌ فشل إنشاء الفاتورة\n{SEP}\n\n"
                "حدث خطأ مع بوابة الدفع. حاول مجدداً أو اختر طريقة أخرى.",
                reply_markup=InlineKeyboardMarkup([
                    [MB("⬅️ رجوع", f"dep_country_{country}", "btn_back")]
                ])
            )
            return ConversationHandler.END

        pay_url, inv_id = result
        await q.edit_message_text(
            f"{SEP}\n{flag} {info['name']}\n{SEP}\n\n"
            f"💰 المبلغ: <b>{amount:,.2f} {label}</b>\n"
            f"≈ <b>{usd:.4f} {asset}</b>\n\n"
            f"🔗 اضغط الزر أدناه للدفع عبر @CryptoBot\n"
            f"✅ سيتم شحن رصيدك <b>تلقائياً</b> بعد الدفع.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 ادفع الآن", url=pay_url)],
                [MB("⬅️ رجوع", f"dep_country_{country}", "btn_back")],
            ])
        )
        ctx.user_data.pop("dep", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    # ── مسار يدوي (إيصال) ───────────────────────────
    await q.edit_message_text(
        f"{SEP}\n{flag} {info['name']}\n{SEP}\n\n"
        f"{info['text']}\n\n"
        f"{SEP2}\n"
        f"💰 المبلغ: <b>{amount:,.2f} {label}</b>\n"
        f"≈ <b>{usd:.4f}$</b>\n\n"
        f"📸 قم بالتحويل ثم أرسل <b>صورة الإيصال</b>:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [MB("⬅️ رجوع", f"dep_country_{country}", "btn_back")]
        ])
    )
    return DEP_RECEIPT


# ══════════════════════════════════════════════════════
# 5. استقبال الإيصال → إرسال للأدمن
# ══════════════════════════════════════════════════════

async def handle_proof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u   = update.effective_user
    dep = ctx.user_data.get("dep", {})

    amount   = dep.get("amount", 0)
    usd      = dep.get("amount_usd", 0)
    country  = dep.get("country", "crypto")
    currency = dep.get("currency", "USD")
    method   = dep.get("method", "—")
    flag     = COUNTRY_FLAG.get(country, "🌐")
    label    = COUNTRY_LABEL.get(country, "")
    ctx.user_data.pop("dep", None)
    ctx.user_data.pop("bot_msg", None)

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ قبول",  callback_data=f"dep_ok_{u.id}_{amount}_{currency}"),
        InlineKeyboardButton("❌ رفض",   callback_data=f"dep_no_{u.id}"),
    ]])
    await ctx.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=(
            f"💳 <b>طلب شحن جديد</b>\n\n"
            f"👤 @{u.username or '—'} | 🆔 <code>{u.id}</code>\n"
            f"{flag} <b>{method}</b>\n"
            f"💰 {amount:,.2f} {label}\n"
            f"≈ <b>{usd:.4f}$</b>"
        ),
        reply_markup=kb,
        parse_mode="HTML"
    )
    await update.message.reply_text(
        "✅ <b>تم إرسال الطلب!</b>\n⏳ سيتم الشحن بعد مراجعة الأدمن.",
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("dep", None)
    ctx.user_data.pop("bot_msg", None)
    if update.message:
        await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════
# 6. قبول / رفض من الأدمن
# ══════════════════════════════════════════════════════

async def dep_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return
    await q.answer()
    parts    = q.data.split("_")
    uid      = int(parts[2])
    amount   = float(parts[3])
    currency = parts[4]
    usd      = convert_to_usd(amount, currency)
    add_balance(uid, usd, f"شحن يدوي ({amount} {currency})", "إيداع")

    # ── عمولة الإحالة ─────────────────────────────────────────────────────
    referrer_id = get_referrer(uid)
    if referrer_id and referrer_id != uid:
        percent    = get_ref_percent()
        commission = round(usd * percent / 100, 6)
        if commission > 0:
            add_balance(referrer_id, commission,
                        f"عمولة إحالة — شحن يدوي ({amount} {currency})",
                        "عمولة")
            try:
                await ctx.bot.send_message(
                    chat_id=referrer_id,
                    text=(
                        f"🎉 <b>تم إضافة عمولة إحالة!</b>\n\n"
                        f"💰 <b>+{commission:.4f}$</b> ({percent:.1f}%)\n"
                        f"من شحن أحد مستخدميك 🌹"
                    ),
                    parse_mode="HTML"
                )
            except Exception as notify_err:
                log.warning(f"فشل إرسال إشعار عمولة → {referrer_id}: {notify_err}")
    elif referrer_id == uid:
        log.warning(f"self-referral مُتجاهَل: uid={uid}")

    await q.edit_message_caption(
        caption=q.message.caption + "\n\n✅ <b>تم القبول والشحن</b>",
        parse_mode="HTML"
    )
    try:
        sym = CURRENCY_SYMBOLS.get(currency, currency)
        await ctx.bot.send_message(
            uid,
            f"✅ <b>تم شحن رصيدك!</b>\n\n"
            f"💰 {amount:,.2f} {sym} ≈ <b>{usd:.4f}$</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass


async def dep_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return
    await q.answer()
    uid = int(q.data.split("_")[2])
    await q.edit_message_caption(
        caption=q.message.caption + "\n\n❌ <b>تم الرفض</b>",
        parse_mode="HTML"
    )
    try:
        await ctx.bot.send_message(uid, "❌ تم رفض طلب الشحن. تواصل مع الدعم.")
    except Exception:
        pass


# ══════════════════════════════════════════════════════
# 7. تجميع الـ handlers
# ══════════════════════════════════════════════════════

deposit_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(show_amounts, pattern="^dep_country_"),
    ],
    states={
        DEP_AMOUNT: [
            CallbackQueryHandler(select_preset, pattern="^dep_amt_"),
            CallbackQueryHandler(ask_custom,    pattern="^dep_custom_"),
            CallbackQueryHandler(show_amounts,  pattern="^dep_country_"),
        ],
        DEP_CUSTOM: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, recv_custom_amount),
            CallbackQueryHandler(show_amounts,  pattern="^dep_country_"),
            CallbackQueryHandler(ask_custom,    pattern="^dep_custom_"),
        ],
        DEP_METHOD: [
            CallbackQueryHandler(show_details,  pattern="^dep_method_"),
            CallbackQueryHandler(show_amounts,  pattern="^dep_country_"),
            CallbackQueryHandler(select_preset, pattern="^dep_amt_"),
        ],
        DEP_RECEIPT: [
            MessageHandler(filters.PHOTO, handle_proof),
            CallbackQueryHandler(show_amounts,  pattern="^dep_country_"),
            CallbackQueryHandler(show_details,  pattern="^dep_method_"),
        ],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_conv),
        CallbackQueryHandler(deposit_menu, pattern="^deposit$"),
    ],
    per_message=False,
    allow_reentry=True,
)

deposit_handler = CallbackQueryHandler(deposit_menu,  pattern="^deposit$")
dep_ok_handler  = CallbackQueryHandler(dep_approve,   pattern="^dep_ok_")
dep_no_handler  = CallbackQueryHandler(dep_reject,    pattern="^dep_no_")


# ══════════════════════════════════════════════════════
# 8. شحن بالنجوم (Telegram Stars / XTR)
# ══════════════════════════════════════════════════════

STARS_AMOUNTS_USD = [1, 3, 5, 10, 25, 50]
WAIT_STARS_USD    = 60   # حالة إدخال مبلغ مخصص


def _stars_rate() -> float:
    """معدل النجوم لكل دولار (100 نجمة = 1.3$  →  rate ≈ 76.9)."""
    try:
        v = get_price("stars_per_usd")
        return max(0.1, float(v)) if v else round(100 / 1.3, 4)
    except Exception:
        return round(100 / 1.3, 4)


async def stars_deposit_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """قائمة اختيار المبلغ للشحن بالنجوم."""
    q = update.callback_query
    await q.answer()
    rate   = _stars_rate()
    price_per_100 = round(100 / rate, 2)
    rows   = []
    pair   = []
    for usd in STARS_AMOUNTS_USD:
        stars = max(1, int(usd * rate))
        pair.append(InlineKeyboardButton(
            f"{usd}$ = {stars} ⭐",
            callback_data=f"dep_stars_{usd}"
        ))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("🔢 كمية مخصصة", callback_data="dep_stars_custom")])
    rows.append([MB("⬅️ رجوع", "deposit", "btn_back")])
    await q.edit_message_text(
        f"{SEP}\n⭐ الشحن بنجوم تيليجرام\n{SEP}\n\n"
        f"💱 معدل الصرف: <b>100 ⭐ = {price_per_100}$</b>\n\n"
        "اختر المبلغ بالدولار وسيتم إرسال فاتورة النجوم:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def stars_create_invoice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إنشاء فاتورة XTR وإرسالها للمستخدم."""
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    usd = float(q.data.replace("dep_stars_", ""))
    rate  = _stars_rate()
    stars = max(1, int(usd * rate))

    payload = f"stars_dep|{uid}|{usd}"
    try:
        await ctx.bot.send_invoice(
            chat_id=uid,
            title="⭐ شحن رصيد المتجر",
            description=f"شحن {usd}$ عبر نجوم تيليجرام ({stars} ⭐)",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("شحن الرصيد", stars)],
        )
        await q.edit_message_text(
            f"{SEP}\n⭐ فاتورة النجوم\n{SEP}\n\n"
            f"💰 المبلغ: <b>{usd}$</b> = <b>{stars} ⭐</b>\n\n"
            "📲 تم إرسال فاتورة النجوم — اضغط عليها للدفع مباشرةً!",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [MB("⬅️ رجوع", "dep_stars_menu", "btn_back")]
            ])
        )
    except Exception as e:
        await q.edit_message_text(
            f"❌ فشل إنشاء الفاتورة: {e}\n\nحاول مجدداً.",
            reply_markup=InlineKeyboardMarkup([
                [MB("⬅️ رجوع", "dep_stars_menu", "btn_back")]
            ])
        )


async def stars_custom_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """طلب مبلغ مخصص بالدولار لشحن النجوم."""
    q = update.callback_query
    await q.answer()
    rate = _stars_rate()
    price_per_100 = round(100 / rate, 2)
    await q.edit_message_text(
        f"{SEP}\n🔢 كمية مخصصة\n{SEP}\n\n"
        f"💱 المعدل: <b>100 ⭐ = {price_per_100}$</b>\n\n"
        "أرسل المبلغ بالدولار الذي تريد شحنه\n"
        "<i>مثال: 7.5 أو 15 أو 100</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            MB("🔙 رجوع", "dep_stars_menu", "btn_back")
        ]])
    )
    return WAIT_STARS_USD


async def stars_custom_process(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة المبلغ المخصص → إنشاء فاتورة نجوم."""
    uid  = update.message.from_user.id
    text = update.message.text.strip().replace(",", ".")
    try:
        usd = float(text)
    except ValueError:
        await update.message.reply_text(
            "❌ أرسل رقماً صحيحاً فقط (مثال: 7.5)",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="dep_stars_menu")
            ]])
        )
        return WAIT_STARS_USD

    if usd < 0.1:
        await update.message.reply_text("❌ الحد الأدنى 0.1$")
        return WAIT_STARS_USD
    if usd > 10000:
        await update.message.reply_text("❌ الحد الأقصى 10,000$")
        return WAIT_STARS_USD

    rate  = _stars_rate()
    stars = max(1, int(usd * rate))
    payload = f"stars_dep|{uid}|{usd}"
    try:
        await ctx.bot.send_invoice(
            chat_id=uid,
            title="⭐ شحن رصيد المتجر",
            description=f"شحن {usd}$ عبر نجوم تيليجرام ({stars} ⭐)",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice("شحن الرصيد", stars)],
        )
        await update.message.reply_text(
            f"✅ <b>تم إرسال الفاتورة</b>\n\n"
            f"💰 المبلغ: <b>{usd}$</b>\n"
            f"⭐ النجوم: <b>{stars} ⭐</b>\n\n"
            "اضغط على الفاتورة أعلاه للدفع.",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ فشل إنشاء الفاتورة: {e}")
    return ConversationHandler.END


async def pre_checkout_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الموافقة التلقائية على كل طلبات الدفع بالنجوم."""
    await update.pre_checkout_query.answer(ok=True)


async def successful_stars_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالجة الدفع الناجح بالنجوم وشحن الرصيد."""
    payment = update.message.successful_payment
    if not payment or payment.currency != "XTR":
        return

    payload = payment.invoice_payload or ""
    if not payload.startswith("stars_dep|"):
        return

    try:
        _, uid_str, usd_str = payload.split("|")
        uid = int(uid_str)
        usd = float(usd_str)
    except Exception:
        return

    add_balance(uid, usd, f"شحن نجوم تيليجرام ({usd:.4f}$)", "إيداع")

    # عمولة الإحالة
    referrer = get_referrer(uid)
    if referrer and referrer != uid:
        pct = get_ref_percent()
        com = round(usd * pct / 100, 6)
        if com > 0:
            add_balance(referrer, com,
                        f"عمولة إحالة — شحن نجوم ({usd:.4f}$)",
                        "عمولة")
            try:
                await ctx.bot.send_message(
                    chat_id=referrer,
                    text=(
                        f"🎉 <b>تم إضافة عمولة إحالة!</b>\n\n"
                        f"💰 <b>+{com:.4f}$</b> ({pct:.1f}%)\n"
                        f"من شحن أحد مستخدميك 🌹"
                    ),
                    parse_mode="HTML"
                )
            except Exception as notify_err:
                log.warning(f"فشل إرسال إشعار عمولة → {referrer}: {notify_err}")
    elif referrer == uid:
        log.warning(f"self-referral مُتجاهَل: uid={uid}")

    stars = payment.total_amount
    await update.message.reply_text(
        f"✅ <b>تم شحن رصيدك!</b>\n\n"
        f"⭐ دفعت: <b>{stars} نجمة</b>\n"
        f"💰 تم إضافة: <b>{usd}$</b> لرصيدك",
        parse_mode="HTML"
    )


dep_stars_menu_handler    = CallbackQueryHandler(stars_deposit_menu,  pattern="^dep_stars_menu$")
dep_stars_invoice_handler = CallbackQueryHandler(stars_create_invoice, pattern="^dep_stars_\\d")
dep_stars_precheckout     = PreCheckoutQueryHandler(pre_checkout_handler)
dep_stars_success_handler = MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_stars_payment)

stars_custom_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(stars_custom_ask, pattern="^dep_stars_custom$")],
    states={
        WAIT_STARS_USD: [MessageHandler(filters.TEXT & ~filters.COMMAND, stars_custom_process)],
    },
    fallbacks=[
        CallbackQueryHandler(stars_deposit_menu, pattern="^dep_stars_menu$"),
    ],
    per_message=False,
    name="stars_custom_conv",
)
async def test_pdf(update, context):
    file = generate_statement_pdf(update.effective_user.id, ["عملية تجريبية"])
    await update.message.reply_document(document=open(file, "rb"))

