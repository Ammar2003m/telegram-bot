import asyncio
import re as _re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)

from config import CURRENCY_SYMBOLS, ADMIN_ID
from db import (get_user, get_balance, deduct_balance, is_banned, convert_from_usd,
                create_order, get_price, get_rate, add_fragment_order,
                is_agent_user, get_agent_effective_price)
from keyboards import back, make_btn as MB, admin_edit_row
from handlers.direct_pay import set_dp_ctx, insufficient_kb, insufficient_text
# tglion API — معطّل حتى إشعار آخر

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — —"

# ── حالات المحادثة ──────────────────────────────
WAIT_USERNAME        = 0
WAIT_STARS_QTY       = 1
WAIT_STARS_UN_CUSTOM = 2
WAIT_RUSH_DATA       = 3
WAIT_RUSH_LIKES      = 4
WAIT_RUSH_VIEWS      = 5
WAIT_BOOSTS          = 6
WAIT_TRANSFER_QTY    = 7
WAIT_TRANSFER_TARGET = 8
WAIT_TRANSFER_SRC    = 9
WAIT_BOOSTS_LINK     = 10
WAIT_BOOSTS_CONFIRM  = 11
WAIT_BUY_CONFIRM     = 12
WAIT_RUSH_CONFIRM    = 13
WAIT_RUSH_PREMIUM    = 14


# ── دالة مساعدة: تعديل نفس الرسالة أو إرسال جديدة ──
async def _bot_edit(ctx, chat_id: int, text: str,
                    reply_markup=None, parse_mode: str = "HTML"):
    """تحاول تعديل الرسالة المخزّنة، إن فشلت ترسل جديدة وتخزّن معرفها."""
    bot_msg = ctx.user_data.get("bot_msg", {})
    msg_id  = bot_msg.get("msg_id")
    if msg_id:
        try:
            await ctx.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=text, reply_markup=reply_markup, parse_mode=parse_mode
            )
            return
        except Exception:
            pass
    msg = await ctx.bot.send_message(
        chat_id=chat_id, text=text,
        reply_markup=reply_markup, parse_mode=parse_mode
    )
    ctx.user_data["bot_msg"] = {"chat_id": chat_id, "msg_id": msg.message_id}


async def _del_user_msg(update: Update):
    """تحذف رسالة المستخدم النصية لإبقاء الشات نظيفاً."""
    try:
        await update.message.delete()
    except Exception:
        pass


# ═══════════════════════════════════════════════
# 1)  قائمة GSM الرئيسية
# ═══════════════════════════════════════════════

async def gsm_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    rows = [
        [
            MB("تيليجرام المميز ✅", "premium",              "btn_tg_premium"),
            MB("النجوم ⭐️",          "stars",                "btn_tg_stars"),
        ],
        [
            MB("الرشق 🚀",           "rush_menu",            "btn_tg_rush"),
            MB("نقل أعضاء 🔄",       "transfer",             "btn_tg_transfer"),
        ],
        [
            MB("تعزيزات ⚡️",         "boosts",               "btn_tg_boosts"),
            MB("يوزرات 🆔",           "usernames_shop",       "btn_tg_usernames"),
        ],
        [
            MB("شراء رقم 📲",         "tgl_numbers",          "btn_tg_numbers"),
            MB("💎 مقتنيات رقمية",    "digital_collectibles", "btn_tg_collectibles"),
        ],
        [MB("⬅️ رجوع",              "main_menu",            "btn_back")],
    ]
    rows += admin_edit_row("tg", uid)
    await q.edit_message_text(
        f"{SEP}\n🟦 متجر روز — خدمات تيليجرام\n{SEP}\nاختر الخدمة:",
        reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML"
    )


# ═══════════════════════════════════════════════
# 2)  بريميوم ✅
# ═══════════════════════════════════════════════

async def premium_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    uid      = q.from_user.id
    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    _agent   = is_agent_user(uid)

    def loc(usd):
        return convert_from_usd(usd, currency)

    if _agent:
        p3  = get_agent_effective_price("prem_3m")
        p6  = get_agent_effective_price("prem_6m")
        p12 = get_agent_effective_price("prem_12m")
        ag_note = "\n🧑‍💼 <i>سعر الوكيل مُطبَّق</i>"
    else:
        p3  = get_price("prem_3m")
        p6  = get_price("prem_6m")
        p12 = get_price("prem_12m")
        ag_note = ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"3 شهور  — {loc(p3)}  {sym}",  callback_data=f"buy_p_{p3}")],
        [InlineKeyboardButton(f"6 شهور  — {loc(p6)}  {sym}",  callback_data=f"buy_p_{p6}")],
        [InlineKeyboardButton(f"12 شهر  — {loc(p12)} {sym}",  callback_data=f"buy_p_{p12}")],
        [InlineKeyboardButton("⬅️ رجوع",                        callback_data="gsm")],
    ])
    await q.edit_message_text(
        f"{SEP}\n✅ تيليجرام المميز\n{SEP}{ag_note}\nاختر الباقة:",
        parse_mode="HTML",
        reply_markup=kb
    )


async def ask_premium_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    usd      = float(q.data.split("_")[-1])
    user     = get_user(q.from_user.id)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    local    = convert_from_usd(usd, currency)
    p3, p6, p12 = get_price("prem_3m"), get_price("prem_6m"), get_price("prem_12m")
    months   = {p3: "3 شهور", p6: "6 شهور", p12: "12 شهر"}
    label    = months.get(usd, months.get(round(usd, 2), ""))

    ctx.user_data["buy"]     = {"svc": "premium", "label": label, "usd": usd}
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}

    await q.edit_message_text(
        f"{SEP}\n✅ تيليجرام المميز — {label}\n{SEP2}\n"
        f"💲 السعر: <b>{local} {sym}</b>\n\n"
        f"✏️ أرسل معرف الحساب:\n<code>@username</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="premium")]
        ]),
        parse_mode="HTML"
    )
    return WAIT_USERNAME


async def process_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid      = update.effective_user.id
    username = update.message.text.strip()
    data     = ctx.user_data.get("buy", {})
    usd      = data.get("usd", 0)
    svc      = data.get("svc", "")
    lbl      = data.get("label", "")
    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    price    = convert_from_usd(usd, currency)
    balance  = get_balance(uid)

    await _del_user_msg(update)

    if balance < usd:
        set_dp_ctx(ctx, svc=svc, label=lbl, usd=usd, back_cb="gsm")
        await _bot_edit(
            ctx, uid,
            insufficient_text(balance, usd, currency, sym),
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("buy", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    ctx.user_data["buy"]["username"] = username
    icon = "✅" if "premium" in svc else "⭐"
    await _bot_edit(
        ctx, uid,
        f"{SEP}\n{icon} تأكيد الطلب\n{SEP2}\n"
        f"📦 الخدمة: <b>{lbl}</b>\n"
        f"👤 الحساب: <code>{username}</code>\n"
        f"💲 السعر: <b>{price:.2f} {sym}</b>\n\n"
        f"هل تريد تأكيد الطلب؟",
        reply_markup=InlineKeyboardMarkup([
            [MB("تأكيد ✅", "buy_confirm", "btn_confirm")],
            [MB("إلغاء ❌", "buy_cancel", "btn_cancel")],
        ])
    )
    return WAIT_BUY_CONFIRM


async def confirm_buy(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "buy_cancel":
        ctx.user_data.pop("buy", None)
        ctx.user_data.pop("bot_msg", None)
        await q.edit_message_text(
            "❌ تم إلغاء الطلب.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ العودة للقائمة", callback_data="gsm")]
            ])
        )
        return ConversationHandler.END

    uid      = q.from_user.id
    data     = ctx.user_data.get("buy", {})
    usd      = data.get("usd", 0)
    svc      = data.get("svc", "")
    lbl      = data.get("label", "")
    username = data.get("username", "")
    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    price    = convert_from_usd(usd, currency)
    balance  = get_balance(uid)

    if balance < usd:
        set_dp_ctx(ctx, svc=svc, label=lbl, usd=usd, back_cb="gsm")
        await q.edit_message_text(
            insufficient_text(balance, usd, currency, sym),
            parse_mode="HTML",
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("buy", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    deduct_balance(uid, usd, f"شراء: {lbl}")
    oid  = create_order(uid, f"{svc} {lbl}", username, usd)
    icon = "✅" if "premium" in svc else "⭐"
    buyer_tag  = f"@{q.from_user.username}" if q.from_user.username else f"ID:{uid}"
    recip_tag  = f"@{username.lstrip('@')}" if username else "—"

    # ── توجيه نجوم / بريميوم للطابور التلقائي ──────────────────────────────
    is_auto = svc in ("stars", "premium")
    if is_auto:
        from fragment_queue import fragment_queue
        # استخراج الكمية أو المدة من التسمية
        _qty_match  = _re.search(r'\d+', lbl or "")
        _qty        = int(_qty_match.group()) if _qty_match else 0
        _duration   = ""
        if svc == "premium":
            if "12" in lbl or "سنة" in lbl:
                _duration = "12"
            elif "6" in lbl:
                _duration = "6"
            else:
                _duration = "3"

        add_fragment_order(
            order_id=oid, user_id=uid, svc=svc,
            username=username, label=lbl, amount_usd=usd,
            amount=_qty if svc == "stars" else 0,
            duration=_duration,
        )
        await fragment_queue.put({
            "oid": oid, "user_id": uid, "svc": svc,
            "username": username, "label": lbl,
            "amount": _qty if svc == "stars" else None,
            "duration": _duration or None,
        })

    await q.edit_message_text("⏳ <b>جاري التنفيذ...</b>", parse_mode="HTML")

    if not is_auto:
        # خدمات أخرى → إشعار أدمن يدوي كما كان
        await _notify_admin(ctx, oid,
            f"{icon} <b>{svc} {lbl} — #{oid}</b>\n"
            f"👤 المشتري: {buyer_tag} (<code>{uid}</code>)\n"
            f"📲 إلى الحساب: <b>{recip_tag}</b>\n"
            f"💲 {usd:.4f}$"
        )

    await asyncio.sleep(1.5)
    auto_note = (
        "⚡ <i>جاري التنفيذ التلقائي — ستتلقى إشعاراً فور الانتهاء</i>"
        if is_auto else
        "⏳ سيُنفَّذ خلال 0–24 ساعة"
    )
    try:
        await q.edit_message_text(
            f"{SEP}\n{icon} تم استلام الطلب\n{SEP2}\n"
            f"📦 <b>{lbl}</b>\n"
            f"👤 <code>{username}</code>\n"
            f"💲 {price:.2f} {sym}\n"
            f"رقم الطلب: <b>#{oid}</b>\n{auto_note}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [MB("⬅️ القائمة الرئيسية", "main_menu", "btn_back_main")]
            ])
        )
    except Exception:
        pass
    ctx.user_data.pop("buy", None)
    ctx.user_data.pop("bot_msg", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# 3)  النجوم ⭐️
# ═══════════════════════════════════════════════

def _stars_usd(qty: int, uid: int = 0) -> float:
    if uid and is_agent_user(uid):
        rate = get_agent_effective_price("stars_1000") if qty >= 1000 else get_agent_effective_price("stars_100")
    else:
        rate = get_price("stars_1000") if qty >= 1000 else get_price("stars_100")
    return round((qty / 100) * rate, 4)


async def stars_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    uid      = q.from_user.id
    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    _agent   = is_agent_user(uid)
    rows = []
    for qty in [100, 200, 500, 1000]:
        usd   = _stars_usd(qty, uid)
        local = convert_from_usd(usd, currency)
        rows.append([InlineKeyboardButton(f"{qty} ⭐  — {local:.2f} {sym}", callback_data=f"stars_{qty}")])
    rows.append([InlineKeyboardButton("✏️ كمية مخصصة", callback_data="stars_custom")])
    rows.append([InlineKeyboardButton("⬅️ رجوع",        callback_data="gsm")])
    if _agent:
        r100  = get_agent_effective_price("stars_100")
        r1000 = get_agent_effective_price("stars_1000")
        ag_note = "\n🧑‍💼 <i>سعر الوكيل مُطبَّق</i>"
    else:
        r100  = get_price("stars_100")
        r1000 = get_price("stars_1000")
        ag_note = ""
    await q.edit_message_text(
        f"{SEP}\n⭐ النجوم\n{SEP2}\n"
        f"السعر: {r100}$ / 100 نجمة (أقل من 1000)\n"
        f"السعر: {r1000}$ / 100 نجمة (1000 فأكثر){ag_note}\n{SEP}\nاختر الكمية:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def ask_stars_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    uid      = q.from_user.id
    qty      = int(q.data.split("_")[1])
    usd      = _stars_usd(qty, uid)
    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    local    = convert_from_usd(usd, currency)

    ctx.user_data["buy"]     = {"svc": "stars", "label": f"{qty} ⭐", "usd": usd}
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}
    await q.edit_message_text(
        f"{SEP}\n⭐ {qty} نجمة\n{SEP2}\n💲 السعر: <b>{local:.2f} {sym}</b>\n\n"
        f"✏️ أرسل معرف الحساب:\n<code>@username</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="stars")]
        ]),
        parse_mode="HTML"
    )
    return WAIT_USERNAME


async def ask_stars_custom_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    ctx.user_data["buy"]     = {"svc": "stars"}
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}
    await q.edit_message_text(
        f"{SEP}\n⭐ نجوم مخصصة\n{SEP}\n✏️ أدخل الكمية (الحد الأدنى 50):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="stars")]
        ])
    )
    return WAIT_STARS_QTY


async def process_stars_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip())
        if qty < 50:
            raise ValueError
    except ValueError:
        await _del_user_msg(update)
        await _bot_edit(ctx, update.effective_user.id, "⚠️ أدخل رقماً صحيحاً (50 أو أكثر).")
        return WAIT_STARS_QTY

    usd      = _stars_usd(qty)
    user     = get_user(update.effective_user.id)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    local    = convert_from_usd(usd, currency)

    await _del_user_msg(update)
    ctx.user_data["buy"].update({"label": f"{qty} ⭐", "usd": usd})
    await _bot_edit(
        ctx, update.effective_user.id,
        f"{SEP}\n⭐ {qty} نجمة — 💲 <b>{local:.2f} {sym}</b>\n{SEP2}\n"
        f"✏️ أرسل معرف الحساب:\n<code>@username</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="stars")]
        ])
    )
    return WAIT_STARS_UN_CUSTOM


async def process_stars_custom_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    return await process_username(update, ctx)


# ═══════════════════════════════════════════════
# 4)  الرشق 🚀
# ═══════════════════════════════════════════════

async def rush_type_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    rows = [
        [MB("رشق أعضاء 👥",           "rush_members",          "btn_rush_members")],
        [MB("رشق أعضاء مميزين 🌟",    "rush_premium_members",  "btn_rush_premium_members")],
        [MB("رشق تفاعلات 👍",         "rush_likes",            "btn_rush_likes")],
        [MB("رشق مشاهدات 👁",         "rush_views",            "btn_rush_views")],
        [MB("⬅️ رجوع",                "gsm",                   "btn_back")],
    ]
    rows += admin_edit_row("gsm_nav", uid)
    await q.edit_message_text(
        f"{SEP}\n🚀 الرشق\n{SEP}\nاختر النوع:",
        reply_markup=InlineKeyboardMarkup(rows)
    )


# ── رشق أعضاء ──────────────────────────────────

async def rush_members_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user     = get_user(q.from_user.id)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    p90  = get_price("member_90")
    p180 = get_price("member_180")
    p365 = get_price("member_365")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ضمان 90  يوم — {convert_from_usd(p90,  currency)} {sym} / 1K",  callback_data="rm_90")],
        [InlineKeyboardButton(f"ضمان 180 يوم — {convert_from_usd(p180, currency)} {sym} / 1K",  callback_data="rm_180")],
        [InlineKeyboardButton(f"ضمان 365 يوم — {convert_from_usd(p365, currency)} {sym} / 1K",  callback_data="rm_365")],
        [InlineKeyboardButton("⬅️ رجوع",                                                          callback_data="rush_menu")],
    ])
    await q.edit_message_text(
        f"{SEP}\n👥 رشق أعضاء\n{SEP2}\nاختر مدة الضمان:",
        reply_markup=kb
    )


async def ask_rush_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    warranty_map = {"rm_90": "member_90", "rm_180": "member_180", "rm_365": "member_365"}
    warranty_day = {"rm_90": 90, "rm_180": 180, "rm_365": 365}
    price_key = warranty_map.get(q.data, "member_90")
    usd_per_k = get_price(price_key)
    days      = warranty_day.get(q.data, 90)
    user      = get_user(q.from_user.id)
    currency  = user["currency"] if user else "USD"
    sym       = CURRENCY_SYMBOLS.get(currency, currency)
    local     = convert_from_usd(usd_per_k, currency)

    ctx.user_data["rush"]    = {"svc": "rush_members", "usd_per_k": usd_per_k, "warranty_days": days}
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}
    await q.edit_message_text(
        f"{SEP}\n👥 رشق أعضاء\n{SEP2}\n"
        f"💲 {local} {sym} لكل 1000 عضو\n\n"
        f"✏️ أرسل في رسالة واحدة:\n"
        f"السطر 1️⃣  رابط القناة أو المجموعة\n"
        f"السطر 2️⃣  الكمية  (مثال: 2000)",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="rush_members")]
        ])
    )
    return WAIT_RUSH_DATA


async def process_rush_members(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _del_user_msg(update)
    lines = update.message.text.strip().splitlines()
    uid = update.effective_user.id

    if len(lines) < 2:
        await _bot_edit(ctx, uid, "⚠️ أرسل الرابط والكمية في رسالة واحدة (سطرين).")
        return WAIT_RUSH_DATA

    link = lines[0].strip()
    try:
        qty = int(lines[1].strip().replace(",", ""))
        if qty < 100:
            raise ValueError
    except ValueError:
        await _bot_edit(ctx, uid, "⚠️ الكمية يجب أن تكون رقماً (100 أو أكثر).")
        return WAIT_RUSH_DATA

    rush      = ctx.user_data.get("rush", {})
    usd_per_k = rush.get("usd_per_k", 2)
    days      = rush.get("warranty_days", 90)
    usd       = round((qty / 1000) * usd_per_k, 4)
    user      = get_user(uid)
    currency  = user["currency"] if user else "USD"
    sym       = CURRENCY_SYMBOLS.get(currency, currency)
    price     = convert_from_usd(usd, currency)
    balance   = get_balance(uid)

    if balance < usd:
        set_dp_ctx(ctx, svc="rush_members", label=f"رشق أعضاء ({qty} عضو)", usd=usd, back_cb="gsm")
        await _bot_edit(
            ctx, uid,
            insufficient_text(balance, usd, currency, sym),
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("rush", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    ctx.user_data["rush"].update({"qty": qty, "link": link, "usd": usd})
    await _bot_edit(
        ctx, uid,
        f"{SEP}\n👥 تأكيد الطلب\n{SEP2}\n"
        f"👥 الكمية: <b>{qty}</b> عضو\n"
        f"🔗 الرابط: <code>{link}</code>\n"
        f"🛡 الضمان: <b>{days}</b> يوم\n"
        f"💲 السعر: <b>{price:.2f} {sym}</b>\n\n"
        f"هل تريد تأكيد الطلب؟",
        reply_markup=InlineKeyboardMarkup([
            [MB("تأكيد ✅", "rush_confirm", "btn_confirm")],
            [MB("إلغاء ❌", "rush_cancel", "btn_cancel")],
        ])
    )
    return WAIT_RUSH_CONFIRM


# ── رشق تفاعلات 👍 ──────────────────────────────

REACTIONS = {
    "like_👍":        ("👍 لايك",            "positive"),
    "like_👎":        ("👎 ديسلايك",         "negative"),
    "like_🤝":        ("🤝 تعاون",           "positive"),
    "like_😂":        ("😂 ضحك",             "positive"),
    "like_⚡":        ("⚡ تفاعل",           "positive"),
    "like_🎉":        ("🎉 احتفال",          "positive"),
    "like_🤩":        ("🤩 إعجاب",           "positive"),
    "like_negative":  ("❌ سلبي 🤬🤮💩",     "negative"),
    "like_positive":  ("✅ إيجابي 🎉🤩👍⚡",  "positive"),
}

async def rush_likes_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("👍 لايك",                        callback_data="like_👍")],
        [InlineKeyboardButton("👎 ديسلايك",                     callback_data="like_👎")],
        [InlineKeyboardButton("🤝 تعاون",                       callback_data="like_🤝")],
        [InlineKeyboardButton("😂 ضحك",                         callback_data="like_😂")],
        [InlineKeyboardButton("⚡ تفاعل",                       callback_data="like_⚡")],
        [InlineKeyboardButton("🎉 احتفال",                      callback_data="like_🎉")],
        [InlineKeyboardButton("🤩 إعجاب",                       callback_data="like_🤩")],
        [InlineKeyboardButton("❌ سلبي  🤬🤮💩",                callback_data="like_negative")],
        [InlineKeyboardButton("✅ إيجابي 🎉🤩👍⚡",             callback_data="like_positive")],
        [InlineKeyboardButton("⬅️ رجوع",                        callback_data="rush_menu")],
    ])
    await q.edit_message_text(
        f"{SEP}\n👍 رشق تفاعلات تيليجرام\n{SEP2}\n"
        f"💲 0.10$ لكل 1000 تفاعل\n{SEP}\nاختر نوع التفاعل:",
        reply_markup=kb
    )


async def ask_likes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """دخول محادثة التفاعلات — entry لـ like_*"""
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    reaction_key  = q.data
    reaction_name = REACTIONS.get(reaction_key, (reaction_key, ""))[0]
    user       = get_user(q.from_user.id)
    currency   = user["currency"] if user else "USD"
    sym        = CURRENCY_SYMBOLS.get(currency, currency)
    rate_likes = get_price("like_1000")
    local      = convert_from_usd(rate_likes, currency)
    ctx.user_data["rush"]    = {"svc": "rush_likes", "usd_per_k": rate_likes, "reaction": reaction_name}
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}
    await q.edit_message_text(
        f"{SEP}\n{reaction_name}\n{SEP2}\n"
        f"💲 {local} {sym} لكل 1000 تفاعل\n\n"
        f"✏️ أرسل في رسالة واحدة:\n"
        f"السطر 1️⃣  الكمية  (مثال: 1000)\n"
        f"السطر 2️⃣  رابط المنشور",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="rush_likes")]
        ])
    )
    return WAIT_RUSH_LIKES


async def process_rush_likes(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _del_user_msg(update)
    lines = update.message.text.strip().splitlines()
    uid   = update.effective_user.id

    if len(lines) < 2:
        await _bot_edit(ctx, uid, "⚠️ أرسل الكمية والرابط في رسالة واحدة (سطرين).")
        return WAIT_RUSH_LIKES

    try:
        qty  = int(lines[0].strip().replace(",", ""))
        if qty < 100:
            raise ValueError
    except ValueError:
        await _bot_edit(ctx, uid, "⚠️ الكمية يجب أن تكون رقماً (100 أو أكثر).")
        return WAIT_RUSH_LIKES

    link      = lines[1].strip()
    rush      = ctx.user_data.get("rush", {})
    usd_per_k = rush.get("usd_per_k", 0.10)
    reaction  = rush.get("reaction", "تفاعل")
    usd       = round((qty / 1000) * usd_per_k, 4)
    user      = get_user(uid)
    currency  = user["currency"] if user else "USD"
    sym       = CURRENCY_SYMBOLS.get(currency, currency)
    price     = convert_from_usd(usd, currency)
    balance   = get_balance(uid)

    if balance < usd:
        set_dp_ctx(ctx, svc="rush_likes", label=f"رشق تفاعلات {reaction} ({qty})", usd=usd, back_cb="gsm")
        await _bot_edit(
            ctx, uid,
            insufficient_text(balance, usd, currency, sym),
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("rush", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    ctx.user_data["rush"].update({"qty": qty, "link": link, "usd": usd})
    await _bot_edit(
        ctx, uid,
        f"{SEP}\n👍 تأكيد الطلب\n{SEP2}\n"
        f"💬 النوع: <b>{reaction}</b>\n"
        f"🔢 الكمية: <b>{qty}</b>\n"
        f"🔗 الرابط: <code>{link}</code>\n"
        f"💲 السعر: <b>{price:.2f} {sym}</b>\n\n"
        f"هل تريد تأكيد الطلب؟",
        reply_markup=InlineKeyboardMarkup([
            [MB("تأكيد ✅", "rush_confirm", "btn_confirm")],
            [MB("إلغاء ❌", "rush_cancel", "btn_cancel")],
        ])
    )
    return WAIT_RUSH_CONFIRM


# ── رشق مشاهدات 👁 ──────────────────────────────

VIEW_META = {
    "view_1":  ("منشور واحد",     "post"),
    "view_10": ("آخر 10 منشورات", "channel"),
    "view_20": ("آخر 20 منشور",   "channel"),
    "view_30": ("آخر 30 منشور",   "channel"),
}

def _get_view_plans() -> dict:
    return {k: (get_price(k), lbl, lt) for k, (lbl, lt) in VIEW_META.items()}

async def rush_views_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user     = get_user(q.from_user.id)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    view_plans = _get_view_plans()
    rows = []
    for key, (rate, label, _) in view_plans.items():
        local = convert_from_usd(rate, currency)
        rows.append([InlineKeyboardButton(f"{label} — {local} {sym} / 1K", callback_data=key)])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="rush_menu")])

    await q.edit_message_text(
        f"{SEP}\n👁 رشق مشاهدات تيليجرام\n{SEP}\nاختر النوع:",
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def ask_views(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """دخول محادثة المشاهدات — entry لـ view_*"""
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    plan_key               = q.data
    view_plans             = _get_view_plans()
    rate, label, link_type = view_plans.get(plan_key, (0.03, "منشور واحد", "post"))
    user                  = get_user(q.from_user.id)
    currency              = user["currency"] if user else "USD"
    sym                   = CURRENCY_SYMBOLS.get(currency, currency)
    local                 = convert_from_usd(rate, currency)

    ctx.user_data["rush"]    = {
        "svc": "rush_views", "usd_per_k": rate,
        "label": label, "link_type": link_type
    }
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}

    link_hint = "رابط المنشور" if link_type == "post" else "رابط القناة"
    await q.edit_message_text(
        f"{SEP}\n👁 {label}\n{SEP2}\n"
        f"💲 {local} {sym} لكل 1000 مشاهدة\n\n"
        f"✏️ أرسل في رسالة واحدة:\n"
        f"السطر 1️⃣  الكمية  (مثال: 5000)\n"
        f"السطر 2️⃣  {link_hint}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="rush_views")]
        ])
    )
    return WAIT_RUSH_VIEWS


async def process_rush_views(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _del_user_msg(update)
    lines = update.message.text.strip().splitlines()
    uid   = update.effective_user.id

    if len(lines) < 2:
        await _bot_edit(ctx, uid, "⚠️ أرسل الكمية والرابط في رسالة واحدة (سطرين).")
        return WAIT_RUSH_VIEWS

    try:
        qty = int(lines[0].strip().replace(",", ""))
        if qty < 100:
            raise ValueError
    except ValueError:
        await _bot_edit(ctx, uid, "⚠️ الكمية يجب أن تكون رقماً (100 أو أكثر).")
        return WAIT_RUSH_VIEWS

    link      = lines[1].strip()
    rush      = ctx.user_data.get("rush", {})
    usd_per_k = rush.get("usd_per_k", 0.03)
    label     = rush.get("label", "مشاهدات")
    usd       = round((qty / 1000) * usd_per_k, 4)
    user      = get_user(uid)
    currency  = user["currency"] if user else "USD"
    sym       = CURRENCY_SYMBOLS.get(currency, currency)
    price     = convert_from_usd(usd, currency)
    balance   = get_balance(uid)

    if balance < usd:
        set_dp_ctx(ctx, svc="rush_views", label=f"رشق {label} ({qty})", usd=usd, back_cb="gsm")
        await _bot_edit(
            ctx, uid,
            insufficient_text(balance, usd, currency, sym),
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("rush", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    ctx.user_data["rush"].update({"qty": qty, "link": link, "usd": usd})
    await _bot_edit(
        ctx, uid,
        f"{SEP}\n👁 تأكيد الطلب\n{SEP2}\n"
        f"📋 النوع: <b>{label}</b>\n"
        f"🔢 الكمية: <b>{qty}</b>\n"
        f"🔗 الرابط: <code>{link}</code>\n"
        f"💲 السعر: <b>{price:.2f} {sym}</b>\n\n"
        f"هل تريد تأكيد الطلب؟",
        reply_markup=InlineKeyboardMarkup([
            [MB("تأكيد ✅", "rush_confirm", "btn_confirm")],
            [MB("إلغاء ❌", "rush_cancel", "btn_cancel")],
        ])
    )
    return WAIT_RUSH_CONFIRM


async def confirm_rush(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالج تأكيد جميع خدمات الرشق (أعضاء / لايكات / مشاهدات)."""
    q = update.callback_query
    await q.answer()

    if q.data == "rush_cancel":
        ctx.user_data.pop("rush", None)
        ctx.user_data.pop("bot_msg", None)
        await q.edit_message_text(
            "❌ تم إلغاء الطلب.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ العودة للقائمة", callback_data="gsm")]
            ])
        )
        return ConversationHandler.END

    uid      = q.from_user.id
    rush     = ctx.user_data.get("rush", {})
    svc      = rush.get("svc", "")
    qty      = rush.get("qty", 0)
    link     = rush.get("link", "")
    usd      = rush.get("usd", 0)
    days     = rush.get("warranty_days", 0)
    reaction = rush.get("reaction", "")
    label    = rush.get("label", "")
    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    price    = convert_from_usd(usd, currency)
    balance  = get_balance(uid)

    if balance < usd:
        set_dp_ctx(ctx, svc=svc, label=label or rush.get("label", "رشق"), usd=usd, back_cb="gsm")
        await q.edit_message_text(
            insufficient_text(balance, usd, currency, sym),
            parse_mode="HTML",
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("rush", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    deduct_balance(uid, usd, f"شراء: رشق ({svc})")

    buyer_tag = f"@{q.from_user.username}" if q.from_user.username else f"ID:{uid}"
    if svc in ("rush_members", "rush_premium_members"):
        prem_tag   = " مميزين 🌟" if svc == "rush_premium_members" else ""
        order_name = f"رشق أعضاء{prem_tag} ({qty}) — ضمان {days} يوم"
        icon_h     = "🌟" if svc == "rush_premium_members" else "👥"
        admin_msg  = (f"{icon_h} <b>رشق أعضاء{prem_tag} — #{{oid}}</b>\n"
                      f"👤 المشتري: {buyer_tag} (<code>{uid}</code>)\n"
                      f"🔗 {link}\n👥 {qty} | ضمان {days} يوم\n💲 {usd:.4f}$")
        icon = icon_h
    elif svc == "rush_likes":
        order_name = f"تفاعلات {reaction} ({qty})"
        admin_msg  = (f"👍 <b>تفاعلات — #{{oid}}</b>\n👤 <code>{uid}</code>\n"
                      f"💬 {reaction}\n🔗 {link}\n🔢 {qty}\n💲 {usd:.4f}$")
        icon = "👍"
    else:
        order_name = f"مشاهدات {label} ({qty})"
        admin_msg  = (f"👁 <b>مشاهدات — #{{oid}}</b>\n👤 <code>{uid}</code>\n"
                      f"📋 {label}\n🔗 {link}\n🔢 {qty}\n💲 {usd:.4f}$")
        icon = "👁"

    oid = create_order(uid, order_name, link, usd)
    await q.edit_message_text(
        f"{SEP}\n{icon} تم إرسال الطلب\n{SEP2}\n"
        f"🔢 الكمية: <b>{qty}</b>\n"
        f"💲 {price:.2f} {sym}\n"
        f"رقم الطلب: <b>#{oid}</b>\n⏳ سيُنفَّذ خلال 0–24 ساعة",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [MB("⬅️ القائمة الرئيسية", "main_menu", "btn_back_main")]
        ])
    )
    await _notify_admin(ctx, oid, admin_msg.replace("{oid}", str(oid)))
    ctx.user_data.pop("rush", None)
    ctx.user_data.pop("bot_msg", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# 5)  التعزيزات ⚡️
# ═══════════════════════════════════════════════

async def boosts_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    user       = get_user(q.from_user.id)
    currency   = user["currency"] if user else "USD"
    sym        = CURRENCY_SYMBOLS.get(currency, currency)
    boost_rate = get_price("boost_10")
    local      = convert_from_usd(boost_rate, currency)
    ctx.user_data["boost"]   = {"currency": currency, "rate": boost_rate}
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}
    await q.edit_message_text(
        f"{SEP}\n⚡ تعزيزات تيليجرام\n{SEP2}\n"
        f"💲 <b>{local} {sym}</b> لكل 10 تعزيزات\n"
        f"📌 الحد الأدنى: 10 | الكمية مضاعف 10 فقط\n\n"
        f"✏️ أرسل العدد (مثال: 10 / 20 / 50):",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="gsm")]
        ]),
        parse_mode="HTML"
    )
    return WAIT_BOOSTS


async def process_boosts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 1: استقبال الكمية → طلب رابط القناة"""
    await _del_user_msg(update)
    uid = update.effective_user.id
    try:
        qty = int(update.message.text.strip())
        if qty < 10 or qty % 10 != 0:
            raise ValueError
    except ValueError:
        await _bot_edit(ctx, uid, "⚠️ العدد يجب أن يكون مضاعف 10 (10، 20، 50 ...).")
        return WAIT_BOOSTS

    ctx.user_data["boost"]["qty"] = qty
    await _bot_edit(
        ctx, uid,
        f"{SEP}\n🔗 أرسل رابط القناة\n{SEP2}\n"
        f"مثال: https://t.me/yourchannel",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="boosts")]
        ])
    )
    return WAIT_BOOSTS_LINK


async def process_boosts_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: استقبال الرابط → عرض ملخص + تأكيد"""
    await _del_user_msg(update)
    link       = update.message.text.strip()
    uid        = update.effective_user.id
    boost_data = ctx.user_data.get("boost", {})
    qty        = boost_data.get("qty", 10)
    boost_rate = boost_data.get("rate", get_price("boost_10"))
    currency   = boost_data.get("currency", "USD")
    sym        = CURRENCY_SYMBOLS.get(currency, currency)
    usd        = round((qty / 10) * boost_rate, 4)
    price      = convert_from_usd(usd, currency)

    ctx.user_data["boost"]["link"] = link
    ctx.user_data["boost"]["usd"]  = usd

    await _bot_edit(
        ctx, uid,
        f"{SEP}\n📊 تفاصيل الطلب\n{SEP2}\n"
        f"⚡ الكمية : <b>{qty}</b> تعزيز\n"
        f"🔗 الرابط : <code>{link}</code>\n"
        f"💲 السعر  : <b>{price:.2f} {sym}</b>\n\n"
        f"هل تريد تأكيد الطلب؟",
        reply_markup=InlineKeyboardMarkup([
            [MB("تأكيد ✅", "boost_confirm", "btn_confirm")],
            [MB("إلغاء ❌", "boost_cancel", "btn_cancel")],
        ])
    )
    return WAIT_BOOSTS_CONFIRM


async def process_boosts_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 3: تأكيد أو إلغاء — الخصم هنا فقط"""
    q = update.callback_query
    await q.answer()

    if q.data == "boost_cancel":
        ctx.user_data.pop("boost", None)
        ctx.user_data.pop("bot_msg", None)
        await q.edit_message_text(
            "❌ تم إلغاء الطلب.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ العودة للقائمة", callback_data="gsm")]
            ])
        )
        return ConversationHandler.END

    uid        = q.from_user.id
    boost_data = ctx.user_data.get("boost", {})
    qty        = boost_data.get("qty", 10)
    link       = boost_data.get("link", "—")
    usd        = boost_data.get("usd", 0)
    currency   = boost_data.get("currency", "USD")
    sym        = CURRENCY_SYMBOLS.get(currency, currency)
    price      = convert_from_usd(usd, currency)
    balance    = get_balance(uid)

    if balance < usd:
        set_dp_ctx(ctx, svc="boosts", label=f"تعزيزات ({qty} ⚡)", usd=usd, back_cb="gsm")
        await q.edit_message_text(
            insufficient_text(balance, usd, currency, sym),
            parse_mode="HTML",
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("boost", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END

    deduct_balance(uid, usd, f"شراء: تعزيزات ({qty} ⚡)")
    oid = create_order(uid, f"تعزيزات ({qty} ⚡)", link, usd)
    await q.edit_message_text(
        f"{SEP}\n✅ تم إرسال الطلب\n{SEP2}\n"
        f"⚡ <b>{qty}</b> تعزيز\n"
        f"🔗 <code>{link}</code>\n"
        f"💲 {price:.2f} {sym}\n"
        f"رقم الطلب: <b>#{oid}</b>\n⏳ سيُنفَّذ خلال 0–24 ساعة",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [MB("⬅️ القائمة الرئيسية", "main_menu", "btn_back_main")]
        ])
    )
    await _notify_admin(ctx, oid,
        f"⚡ <b>تعزيزات — #{oid}</b>\n"
        f"👤 <code>{uid}</code>\n"
        f"⚡ {qty} | 🔗 {link}\n"
        f"💲 {usd:.4f}$"
    )
    ctx.user_data.pop("boost", None)
    ctx.user_data.pop("bot_msg", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# 6)  نقل أعضاء (قريباً)
# ═══════════════════════════════════════════════

async def transfer_entry(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """نقطة دخول خدمة نقل الأعضاء"""
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    user     = get_user(q.from_user.id)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    rate     = get_price("transfer_1000")
    local    = convert_from_usd(rate, currency)

    ctx.user_data["transfer"] = {"currency": currency, "rate": rate}
    await q.message.reply_text(
        f"{SEP}\n🔄 نقل أعضاء\n{SEP2}\n"
        f"💲 <b>{local} {sym}</b> لكل 1000 عضو\n"
        f"📌 الحد الأدنى: 100 عضو\n\n"
        f"أرسل الكمية المطلوبة:",
        parse_mode="HTML"
    )
    return WAIT_TRANSFER_QTY


async def handle_transfer_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        qty = int(update.message.text.strip().replace(",", ""))
        if qty < 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقماً صحيحاً (100 أو أكثر).")
        return WAIT_TRANSFER_QTY

    ctx.user_data["transfer"]["qty"] = qty
    await update.message.reply_text(
        f"{SEP}\n🎯 الرابط الهدف\n{SEP2}\n"
        f"أرسل رابط القناة أو المجموعة التي سيُنقل إليها الأعضاء:"
    )
    return WAIT_TRANSFER_TARGET


async def handle_transfer_target(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    target = update.message.text.strip()
    ctx.user_data["transfer"]["target"]  = target
    ctx.user_data["transfer"]["sources"] = []
    await update.message.reply_text(
        f"{SEP}\n📥 روابط المصادر\n{SEP2}\n"
        f"أرسل روابط الجروبات المصدر (رابط واحد أو أكثر في كل رسالة).\n"
        f"عند الانتهاء أرسل: <b>تم</b>",
        parse_mode="HTML"
    )
    return WAIT_TRANSFER_SRC


async def handle_transfer_sources(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text in ("تم", "done", "Done", "تم."):
        return await _finish_transfer(update, ctx)

    # دعم إرسال أكثر من رابط في رسالة واحدة (كل سطر رابط)
    links = [l.strip() for l in text.splitlines() if l.strip()]
    ctx.user_data["transfer"]["sources"].extend(links)
    count = len(ctx.user_data["transfer"]["sources"])
    await update.message.reply_text(
        f"✅ تم حفظ {len(links)} رابط — المجموع: {count}\n"
        f"أرسل المزيد أو اكتب <b>تم</b> للإنهاء.",
        parse_mode="HTML"
    )
    return WAIT_TRANSFER_SRC


async def _finish_transfer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tr = ctx.user_data.get("transfer", {})
    sources = tr.get("sources", [])

    if not sources:
        await update.message.reply_text("⚠️ لم تُرسل أي روابط مصدر. أرسل رابطاً واحداً على الأقل.")
        return WAIT_TRANSFER_SRC

    uid      = update.effective_user.id
    qty      = tr.get("qty", 0)
    rate     = tr.get("rate", get_price("transfer_1000"))
    target   = tr.get("target", "—")
    currency = tr.get("currency", "USD")
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    usd   = round((qty / 1000) * rate, 4)
    price = convert_from_usd(usd, currency)   # للعرض فقط
    bal   = get_balance(uid)                  # بالدولار

    if bal < usd:
        set_dp_ctx(ctx, svc="transfer", label=f"نقل أعضاء ({qty} عضو)", usd=usd, back_cb="gsm")
        await update.message.reply_text(
            insufficient_text(bal, usd, currency, sym),
            parse_mode="HTML",
            reply_markup=insufficient_kb("gsm"),
        )
        ctx.user_data.pop("transfer", None)
        return ConversationHandler.END

    deduct_balance(uid, usd, f"شراء: نقل أعضاء ({qty})")
    sources_text = "\n".join(f"• {s}" for s in sources)
    oid = create_order(uid, f"نقل أعضاء ({qty})", target, usd)

    await update.message.reply_text(
        f"{SEP}\n✅ تم إرسال الطلب\n{SEP2}\n"
        f"👥 <b>{qty}</b> عضو\n"
        f"🎯 الهدف: {target}\n"
        f"📥 المصادر:\n{sources_text}\n"
        f"💲 {price:.2f} {sym}\n"
        f"رقم الطلب: <b>#{oid}</b>",
        parse_mode="HTML"
    )
    await _notify_admin(ctx, oid,
        f"🔄 <b>نقل أعضاء — #{oid}</b>\n"
        f"👤 <code>{uid}</code>\n"
        f"👥 {qty} | 💲 {usd:.4f}$\n"
        f"🎯 الهدف: {target}\n"
        f"📥 المصادر:\n{sources_text}"
    )
    ctx.user_data.pop("transfer", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# رشق أعضاء مميزين 🌟
# ═══════════════════════════════════════════════

async def rush_premium_members_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)
    user     = get_user(q.from_user.id)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    rate     = get_price("rush_premium_1k")
    loc      = convert_from_usd(rate, currency)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"ضمان 30 يوم — {loc:.2f} {sym} / 1000 عضو", callback_data="rpm_30")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="rush_menu")],
    ])
    await q.edit_message_text(
        f"{SEP}\n🌟 رشق أعضاء مميزين\n{SEP2}\n"
        f"✅ ضمان استرداد 30 يوم\n"
        f"💲 {loc:.2f} {sym} لكل 1000 عضو\n\n"
        f"اختر الضمان:",
        reply_markup=kb, parse_mode="HTML"
    )


async def ask_rush_premium_data(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)
    user      = get_user(q.from_user.id)
    currency  = user["currency"] if user else "USD"
    sym       = CURRENCY_SYMBOLS.get(currency, currency)
    usd_per_k = get_price("rush_premium_1k")
    loc       = convert_from_usd(usd_per_k, currency)
    ctx.user_data["rush"]    = {"svc": "rush_premium_members", "usd_per_k": usd_per_k, "warranty_days": 30}
    ctx.user_data["bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}
    await q.edit_message_text(
        f"{SEP}\n🌟 رشق أعضاء مميزين\n{SEP2}\n"
        f"💲 {loc:.2f} {sym} لكل 1000 عضو | ضمان 30 يوم\n\n"
        f"✏️ أرسل في رسالة واحدة:\n"
        f"السطر 1️⃣  الكمية (مثال: 2000)\n"
        f"السطر 2️⃣  رابط القناة أو المجموعة",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ رجوع", callback_data="rush_premium_members")]
        ]),
        parse_mode="HTML"
    )
    return WAIT_RUSH_PREMIUM


async def process_rush_premium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _del_user_msg(update)
    lines = update.message.text.strip().splitlines()
    uid   = update.effective_user.id
    if len(lines) < 2:
        await _bot_edit(ctx, uid, "⚠️ أرسل الكمية والرابط في رسالة واحدة (سطرين).")
        return WAIT_RUSH_PREMIUM
    try:
        qty = int(lines[0].strip().replace(",", ""))
        if qty < 100:
            raise ValueError
    except ValueError:
        await _bot_edit(ctx, uid, "⚠️ الكمية يجب أن تكون رقماً (100 أو أكثر).")
        return WAIT_RUSH_PREMIUM
    link      = lines[1].strip()
    rush      = ctx.user_data.get("rush", {})
    usd_per_k = rush.get("usd_per_k", 7.5)
    days      = rush.get("warranty_days", 30)
    usd       = round((qty / 1000) * usd_per_k, 4)
    user      = get_user(uid)
    currency  = user["currency"] if user else "USD"
    sym       = CURRENCY_SYMBOLS.get(currency, currency)
    price     = convert_from_usd(usd, currency)
    balance   = get_balance(uid)
    if balance < usd:
        set_dp_ctx(ctx, svc="rush_premium_members", label=f"رشق أعضاء مميزين ({qty})", usd=usd, back_cb="gsm")
        await _bot_edit(ctx, uid, insufficient_text(balance, usd, currency, sym), reply_markup=insufficient_kb("gsm"))
        ctx.user_data.pop("rush", None)
        ctx.user_data.pop("bot_msg", None)
        return ConversationHandler.END
    ctx.user_data["rush"].update({"qty": qty, "link": link, "usd": usd})
    await _bot_edit(
        ctx, uid,
        f"{SEP}\n🌟 تأكيد رشق أعضاء مميزين\n{SEP2}\n"
        f"👥 الكمية: <b>{qty}</b> عضو\n"
        f"🔗 الرابط: <code>{link}</code>\n"
        f"🛡 الضمان: <b>{days}</b> يوم\n"
        f"💲 السعر: <b>{price:.2f} {sym}</b>\n\n"
        f"هل تريد تأكيد الطلب؟",
        reply_markup=InlineKeyboardMarkup([
            [MB("تأكيد ✅", "rush_confirm", "btn_confirm")],
            [MB("إلغاء ❌", "rush_cancel",  "btn_cancel")],
        ])
    )
    return WAIT_RUSH_CONFIRM


# ═══════════════════════════════════════════════
# مقتنيات رقمية 💎
# ═══════════════════════════════════════════════

async def digital_collectibles_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)
    await q.edit_message_text(
        f"{SEP}\n💎 مقتنيات رقمية\n{SEP2}\n\n"
        f"لشراء هدايا تيليجرام والمقتنيات الرقمية\n"
        f"يرجى التواصل مع الدعم البشري مباشرة 👇",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 تواصل مع الدعم البشري", url="http://t.me/aaamp")],
            [InlineKeyboardButton("⬅️ رجوع", callback_data="gsm")],
        ]),
        parse_mode="HTML"
    )


async def _notify_admin(ctx: ContextTypes.DEFAULT_TYPE, order_id: int, text: str):
    from db import get_order_group
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ جارٍ المعالجة", callback_data=f"process_{order_id}")],
        [
            InlineKeyboardButton("✅ تم",    callback_data=f"done_{order_id}"),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{order_id}"),
        ],
    ])
    await ctx.bot.send_message(ADMIN_ID, text, reply_markup=kb, parse_mode="HTML")
    try:
        gid = get_order_group()
        if gid:
            await ctx.bot.send_message(gid, text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        pass


async def cancel_conv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    for k in ("buy", "rush", "boost", "bot_msg"):
        ctx.user_data.pop(k, None)
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# قسم أرقام تيليجرام — معطّل حتى إشعار آخر
# ═══════════════════════════════════════════════
async def get_code(update, ctx):
    q = update.callback_query
    await q.answer("الخدمة معطلة حالياً", show_alert=True)

async def tgl_numbers_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """أرقام تيليجرام — معطّل مؤقتاً، توجيه للمالك."""
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    return await q.answer("مؤقتاً معطل", show_alert=True)


# ── Plain Callback Handlers (TG-Lion) ─────────────────────────────
tgl_numbers_handler = CallbackQueryHandler(
    tgl_numbers_menu,
    pattern="^tgl_numbers$"
)
# select_country_handler = CallbackQueryHandler(select_country, pattern="^buy_")
confirm_buy_handler = CallbackQueryHandler(confirm_buy, pattern="^confirm_buy")
# get_code_handler = CallbackQueryHandler(get_code, pattern="^get_code")

# ═══════════════════════════════════════════════
# تجميع الـ handlers
# ═══════════════════════════════════════════════

gsm_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(ask_premium_username,    pattern="^buy_p_"),
        CallbackQueryHandler(ask_stars_username,      pattern="^stars_(100|200|500|1000)$"),
        CallbackQueryHandler(ask_stars_custom_qty,    pattern="^stars_custom$"),
        CallbackQueryHandler(ask_rush_data,           pattern="^rm_"),
        CallbackQueryHandler(ask_rush_premium_data,   pattern="^rpm_"),
        CallbackQueryHandler(ask_likes,               pattern="^like_"),
        CallbackQueryHandler(ask_views,               pattern="^view_"),
        CallbackQueryHandler(boosts_entry,            pattern="^boosts$"),
        CallbackQueryHandler(transfer_entry,          pattern="^transfer$"),
    ],
    states={
        WAIT_USERNAME:        [MessageHandler(filters.TEXT & ~filters.COMMAND, process_username)],
        WAIT_STARS_QTY:       [MessageHandler(filters.TEXT & ~filters.COMMAND, process_stars_qty)],
        WAIT_STARS_UN_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_stars_custom_username)],
        WAIT_RUSH_DATA:       [MessageHandler(filters.TEXT & ~filters.COMMAND, process_rush_members)],
        WAIT_RUSH_PREMIUM:    [MessageHandler(filters.TEXT & ~filters.COMMAND, process_rush_premium)],
        WAIT_RUSH_LIKES:      [MessageHandler(filters.TEXT & ~filters.COMMAND, process_rush_likes)],
        WAIT_RUSH_VIEWS:      [MessageHandler(filters.TEXT & ~filters.COMMAND, process_rush_views)],
        WAIT_BOOSTS:          [MessageHandler(filters.TEXT & ~filters.COMMAND, process_boosts)],
        WAIT_BOOSTS_LINK:     [MessageHandler(filters.TEXT & ~filters.COMMAND, process_boosts_link)],
        WAIT_BOOSTS_CONFIRM:  [CallbackQueryHandler(process_boosts_confirm, pattern="^boost_(confirm|cancel)$")],
        WAIT_BUY_CONFIRM:     [CallbackQueryHandler(confirm_buy,            pattern="^buy_(confirm|cancel)$")],
        WAIT_RUSH_CONFIRM:    [CallbackQueryHandler(confirm_rush,           pattern="^rush_(confirm|cancel)$")],
        WAIT_TRANSFER_QTY:    [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_qty)],
        WAIT_TRANSFER_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_target)],
        WAIT_TRANSFER_SRC:    [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_transfer_sources)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_conv),
        CallbackQueryHandler(digital_collectibles_menu, pattern="^digital_collectibles$"),
    ],
    per_message=False,
    allow_reentry=True,
)

# ── Plain Callback Handlers ──────────────────────────
gsm_handler          = CallbackQueryHandler(gsm_menu,           pattern="^gsm$")
premium_handler      = CallbackQueryHandler(premium_menu,       pattern="^premium$")
stars_handler                 = CallbackQueryHandler(stars_menu,                 pattern="^stars$")
rush_menu_handler             = CallbackQueryHandler(rush_type_menu,             pattern="^rush_menu$")
rush_members_handler          = CallbackQueryHandler(rush_members_menu,          pattern="^rush_members$")
rush_premium_members_handler  = CallbackQueryHandler(rush_premium_members_menu,  pattern="^rush_premium_members$")
rush_likes_handler            = CallbackQueryHandler(rush_likes_menu,            pattern="^rush_likes$")
rush_views_handler            = CallbackQueryHandler(rush_views_menu,            pattern="^rush_views$")
digital_collectibles_handler  = CallbackQueryHandler(digital_collectibles_menu,  pattern="^digital_collectibles$")
