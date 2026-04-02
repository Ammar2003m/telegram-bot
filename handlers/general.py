from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)

from config import NETFLIX_PLANS, CURRENCY_SYMBOLS, ADMIN_ID
from db import get_user, get_balance, deduct_balance, is_banned, convert_from_usd, create_order, get_price, get_text
from keyboards import back, make_btn as MB, admin_edit_row
from handlers.direct_pay import set_dp_ctx, insufficient_kb, insufficient_text

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — —"

# ── حالات المحادثة ──────────────────────────────
WAIT_NET_ACC   = 0   # انتظار نوع الحساب (callback)
WAIT_NET_EMAIL = 1   # انتظار الإيميل (نص)


# ═══════════════════════════════════════════════
# القائمة العامة
# ═══════════════════════════════════════════════

async def general_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)
    rows = [
        [
            MB("نتفلكس 🍿",       "svc_netflix", "btn_gen_netflix"),
            MB("شحن ألعاب 🎮",    "games",        "btn_gen_games"),
        ],
        [
            MB("باقات سوا STC 📶", "stc_menu",    "btn_gen_stc"),
        ],
        [MB("🔙 رجوع",           "main_menu",    "btn_back")],
    ]
    rows += admin_edit_row("general", uid)
    heading = get_text("general_menu", "🌐 الخدمات العامة")
    await q.edit_message_text(f"<b>{heading}</b>", reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")


# ═══════════════════════════════════════════════
# نتفلكس
# ═══════════════════════════════════════════════

async def netflix_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    user     = get_user(q.from_user.id)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    lines = [f"{SEP}\n🍿 اشتراك نتفلكس\n{SEP}\n"]
    emojis = ["1️⃣", "2️⃣", "3️⃣"]
    rows   = []

    for i, (key, (lbl, res, devices)) in enumerate(NETFLIX_PLANS.items()):
        usd   = get_price(f"net_{key}")
        local = convert_from_usd(usd, currency)
        lines.append(
            f"{emojis[i]} باقة {lbl}\n"
            f"📺 الدقة: {res}\n"
            f"{'👤' if devices == 1 else '👥'} الأجهزة: {devices}\n"
            f"💰 السعر: {local} {sym}\n"
        )
        rows.append([InlineKeyboardButton(
            f"شراء {lbl} — {local} {sym}", callback_data=f"buy_net_{key}"
        )])

    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="general")])
    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML"
    )


async def ask_netflix_acctype(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 1: اختيار الباقة → اختيار نوع الحساب"""
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    plan_key     = q.data.split("_")[2]          # buy_net_basic → basic
    lbl, res, dv = NETFLIX_PLANS[plan_key]
    usd          = get_price(f"net_{plan_key}")
    user         = get_user(q.from_user.id)
    currency     = user["currency"] if user else "USD"
    sym          = CURRENCY_SYMBOLS.get(currency, currency)
    local        = convert_from_usd(usd, currency)

    ctx.user_data["net"] = {
        "plan": plan_key, "label": lbl,
        "usd": usd, "currency": currency
    }

    kb = InlineKeyboardMarkup([
        [MB("✉️ إيميلي الخاص", "net_acc_own",  "btn_net_own_email")],
        [MB("📧 إيميل جديد",  "net_acc_new",  "btn_net_new_email")],
        [MB("🔙 رجوع",         "svc_netflix",  "btn_back")],
    ])
    await q.message.reply_text(
        f"{SEP}\n🍿 باقة {lbl}\n{SEP2}\n"
        f"📺 {res} | {'👤' if dv == 1 else '👥'} {dv} {'جهاز' if dv == 1 else 'أجهزة'}\n"
        f"💲 <b>{local} {sym}</b>\n\n"
        f"اختر نوع الحساب:",
        reply_markup=kb,
        parse_mode="HTML"
    )
    return WAIT_NET_ACC


async def acc_own_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """المستخدم اختار إيميله الخاص → اطلب الإيميل"""
    q = update.callback_query
    await q.answer()
    ctx.user_data["net"]["acc_type"] = "own"
    await q.message.reply_text(
        f"{SEP}\n✉️ إيميلك الخاص\n{SEP2}\n"
        f"أرسل بريدك الإلكتروني:"
    )
    return WAIT_NET_EMAIL


async def acc_new_selected(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """المستخدم اختار إيميل جديد → نفّذ الطلب مباشرة"""
    q = update.callback_query
    await q.answer()
    ctx.user_data["net"]["acc_type"] = "new"
    return await _process_netflix_order(
        update=update, ctx=ctx,
        uid=q.from_user.id,
        email="إيميل جديد من المتجر"
    )


async def process_netflix_email(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال الإيميل الخاص ونفّذ الطلب"""
    email = update.message.text.strip()
    uid   = update.effective_user.id
    return await _process_netflix_order(update, ctx, uid, email)


async def _process_netflix_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                                  uid: int, email: str):
    """المنطق المشترك لإنشاء الطلب وخصم الرصيد"""
    data     = ctx.user_data.get("net", {})
    usd      = data.get("usd", 0)
    lbl      = data.get("label", "")
    currency = data.get("currency", "USD")
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    price    = convert_from_usd(usd, currency)   # للعرض فقط
    balance  = get_balance(uid)                  # بالدولار

    if balance < usd:
        set_dp_ctx(ctx, svc="نتفلكس", label=f"نتفلكس {lbl}", usd=usd, back_cb="netflix")
        kb = insufficient_kb("netflix")
        txt = insufficient_text(balance, usd, currency, sym)
        if update.message:
            await update.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)
        else:
            await update.callback_query.message.reply_text(txt, parse_mode="HTML", reply_markup=kb)
        ctx.user_data.pop("net", None)
        return ConversationHandler.END

    deduct_balance(uid, usd, f"شراء: نتفلكس {lbl}")
    oid = create_order(uid, f"نتفلكس {lbl}", email, usd)

    confirm_text = (
        f"{SEP}\n✅ تم إرسال الطلب\n{SEP2}\n"
        f"🍿 نتفلكس <b>{lbl}</b>\n"
        f"✉️ {email}\n"
        f"💲 {price:.2f} {sym}\n"
        f"رقم الطلب: <b>#{oid}</b>\n\n"
        f"⏳ سيتم التفعيل قريباً."
    )
    if update.message:
        await update.message.reply_text(confirm_text, parse_mode="HTML")
    else:
        await update.callback_query.message.reply_text(confirm_text, parse_mode="HTML")

    # إشعار الأدمن
    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تم",    callback_data=f"done_{oid}"),
        InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{oid}"),
    ]])
    await ctx.bot.send_message(
        ADMIN_ID,
        f"🍿 <b>نتفلكس — #{oid}</b>\n"
        f"👤 <code>{uid}</code>\n"
        f"📋 {lbl}\n"
        f"✉️ {email}\n"
        f"💲 {usd:.4f}$",
        reply_markup=kb,
        parse_mode="HTML"
    )
    ctx.user_data.pop("net", None)
    return ConversationHandler.END


async def cancel_netflix(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("net", None)
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END


# ── تجميع الـ handlers ───────────────────────────

netflix_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(ask_netflix_acctype, pattern="^buy_net_")],
    states={
        WAIT_NET_ACC: [
            CallbackQueryHandler(acc_own_selected, pattern="^net_acc_own$"),
            CallbackQueryHandler(acc_new_selected, pattern="^net_acc_new$"),
        ],
        WAIT_NET_EMAIL: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, process_netflix_email)
        ],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_netflix)],
    per_message=False,
    allow_reentry=True,
)

general_handler  = CallbackQueryHandler(general_menu, pattern="^general$")
netflix_handler  = CallbackQueryHandler(netflix_menu, pattern="^svc_netflix$")
