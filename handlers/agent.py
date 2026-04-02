"""
لوحة الوكيل — agent panel
الوكلاء فقط | العملة ثابتة USD | أسعار خاصة
"""
import asyncio
import re as _re
import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters,
)

from config import ADMIN_ID
from db import (
    get_user, get_balance, deduct_balance, is_banned, is_agent_user,
    create_order, get_agent_effective_price, get_all_agent_prices,
    get_price, add_fragment_order,
)

log = logging.getLogger(__name__)

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — —"

# ── حالات المحادثة ─────────────────────────────────────────────
AG_WAIT_STARS_QTY  = 0
AG_WAIT_STARS_UN   = 1
AG_WAIT_STARS_CONF = 2
AG_WAIT_PREM_UN    = 3
AG_WAIT_PREM_CONF  = 4
AG_WAIT_CUSTOM_QTY = 5


# ═══════════════════════════════════════════════════════════════
# دوال مساعدة
# ═══════════════════════════════════════════════════════════════

def _stars_usd_agent(qty: int) -> float:
    rate = get_agent_effective_price("stars_1000") if qty >= 1000 else get_agent_effective_price("stars_100")
    return round((qty / 100) * rate, 4)


def _prem_usd_agent(months: int) -> float:
    key_map = {3: "prem_3m", 6: "prem_6m", 12: "prem_12m"}
    return get_agent_effective_price(key_map.get(months, "prem_3m"))


def _price_line(service: str, label: str) -> str:
    from db import get_agent_price
    ag  = get_agent_price(service)
    reg = get_price(service)
    if ag is not None:
        return f"  • {label}: <b>{ag}$</b> <i>(عادي: {reg}$)</i>"
    return f"  • {label}: <b>{reg}$</b>"


def _check_agent(uid: int) -> bool:
    return is_agent_user(uid)


# ═══════════════════════════════════════════════════════════════
# 1.  لوحة الوكيل الرئيسية
# ═══════════════════════════════════════════════════════════════

async def agent_panel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    if not _check_agent(uid):
        await q.edit_message_text(
            "🚫 <b>غير مصرّح</b>\n\nهذه اللوحة للوكلاء المعتمدين فقط.\n"
            "تواصل مع الإدارة للحصول على صلاحية الوكيل.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ الرئيسية", callback_data="main_menu")]
            ]),
        )
        return

    bal = get_balance(uid)
    user = get_user(uid)
    uname = f"@{user['username']}" if user and user.get("username") else f"ID:{uid}"

    # أسعار الوكيل (مع fallback للسعر العادي)
    r100  = get_agent_effective_price("stars_100")
    r1000 = get_agent_effective_price("stars_1000")
    p3    = get_agent_effective_price("prem_3m")
    p6    = get_agent_effective_price("prem_6m")
    p12   = get_agent_effective_price("prem_12m")

    text = (
        f"<b>{SEP}\n🧑‍💼 لوحة الوكيل\n{SEP}</b>\n\n"
        f"👤 {uname}\n"
        f"💰 رصيدك: <b>{bal:.4f} $</b>\n"
        f"🔒 العملة: <b>USD</b> (ثابتة)\n\n"
        f"<b>{SEP2}\n💲 أسعارك الخاصة:\n{SEP2}</b>\n"
        f"⭐ نجوم — أقل من 1000: <b>{r100}$</b>/100\n"
        f"⭐ نجوم — 1000 فأكثر: <b>{r1000}$</b>/100\n"
        f"✅ بريميوم 3 شهور: <b>{p3}$</b>\n"
        f"✅ بريميوم 6 شهور: <b>{p6}$</b>\n"
        f"✅ بريميوم 12 شهر: <b>{p12}$</b>\n"
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ شراء نجوم",    callback_data="ag_buy_stars"),
            InlineKeyboardButton("✅ شراء بريميوم", callback_data="ag_buy_prem"),
        ],
        [InlineKeyboardButton("⬅️ الرئيسية", callback_data="main_menu")],
    ])
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


# ═══════════════════════════════════════════════════════════════
# 2.  شراء النجوم ⭐
# ═══════════════════════════════════════════════════════════════

async def ag_stars_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if not _check_agent(uid):
        return await q.answer("🚫 غير مصرّح", show_alert=True)

    rows = []
    for qty in [100, 200, 500, 1000, 2000, 5000]:
        usd = _stars_usd_agent(qty)
        rows.append([InlineKeyboardButton(
            f"{qty} ⭐  — {usd:.4f} $", callback_data=f"ag_stars_{qty}"
        )])
    rows.append([InlineKeyboardButton("✏️ كمية مخصصة", callback_data="ag_stars_custom")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="agent_panel")])

    r100  = get_agent_effective_price("stars_100")
    r1000 = get_agent_effective_price("stars_1000")
    await q.edit_message_text(
        f"<b>{SEP}\n⭐ شراء النجوم — سعر الوكيل\n{SEP2}</b>\n"
        f"السعر: <b>{r100}$</b>/100 (أقل من 1000)\n"
        f"السعر: <b>{r1000}$</b>/100 (1000 فأكثر)\n"
        f"<b>{SEP}</b>\nاختر الكمية:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )
    return AG_WAIT_STARS_QTY


async def ag_stars_pick_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if not _check_agent(uid):
        return await q.answer("🚫 غير مصرّح", show_alert=True)

    qty = int(q.data.split("_")[-1])
    usd = _stars_usd_agent(qty)
    ctx.user_data["ag_buy"] = {"svc": "stars", "label": f"{qty} ⭐", "qty": qty, "usd": usd}
    ctx.user_data["ag_bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}

    await q.edit_message_text(
        f"<b>{SEP}\n⭐ {qty} نجمة\n{SEP2}</b>\n"
        f"💲 السعر: <b>{usd:.4f} $</b>\n\n"
        f"✏️ أرسل معرف الحساب:\n<code>@username</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="agent_panel")]
        ]),
    )
    return AG_WAIT_STARS_UN


async def ag_stars_custom_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if not _check_agent(uid):
        return await q.answer("🚫 غير مصرّح", show_alert=True)

    ctx.user_data["ag_bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}
    await q.edit_message_text(
        f"<b>{SEP}\n⭐ كمية مخصصة\n{SEP2}</b>\n"
        f"أرسل عدد النجوم (أدنى 50):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="agent_panel")]
        ]),
    )
    return AG_WAIT_CUSTOM_QTY


async def ag_stars_custom_qty(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_agent(uid):
        return ConversationHandler.END

    txt = update.message.text.strip()
    if not txt.isdigit() or int(txt) < 50:
        await update.message.reply_text("⚠️ أرسل عدداً صحيحاً (50 أو أكثر).")
        return AG_WAIT_CUSTOM_QTY

    qty = int(txt)
    usd = _stars_usd_agent(qty)
    ctx.user_data["ag_buy"] = {"svc": "stars", "label": f"{qty} ⭐", "qty": qty, "usd": usd}

    await update.message.reply_text(
        f"<b>⭐ {qty} نجمة — {usd:.4f} $</b>\n\n"
        f"✏️ أرسل معرف الحساب:\n<code>@username</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="agent_panel")]
        ]),
    )
    return AG_WAIT_STARS_UN


async def ag_stars_recv_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_agent(uid):
        return ConversationHandler.END

    raw      = update.message.text.strip().lstrip("@")
    buy      = ctx.user_data.get("ag_buy", {})
    qty      = buy.get("qty", 0)
    usd      = buy.get("usd", 0.0)
    label    = buy.get("label", "")
    balance  = get_balance(uid)

    if balance < usd:
        await update.message.reply_text(
            f"⚠️ <b>رصيدك غير كافٍ</b>\n\n"
            f"رصيدك: <b>{balance:.4f}$</b>\n"
            f"المطلوب: <b>{usd:.4f}$</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ لوحة الوكيل", callback_data="agent_panel")]
            ]),
        )
        ctx.user_data.pop("ag_buy", None)
        return ConversationHandler.END

    ctx.user_data["ag_buy"]["username"] = raw

    await update.message.reply_text(
        f"<b>{SEP}\n⭐ تأكيد الطلب\n{SEP2}</b>\n"
        f"📦 {label}\n"
        f"👤 <code>@{raw}</code>\n"
        f"💲 <b>{usd:.4f} $</b>\n\n"
        f"هل تؤكد الطلب؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد", callback_data="ag_confirm"),
                InlineKeyboardButton("❌ إلغاء", callback_data="agent_panel"),
            ]
        ]),
    )
    return AG_WAIT_STARS_CONF


# ═══════════════════════════════════════════════════════════════
# 3.  شراء البريميوم ✅
# ═══════════════════════════════════════════════════════════════

async def ag_prem_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if not _check_agent(uid):
        return await q.answer("🚫 غير مصرّح", show_alert=True)

    p3  = _prem_usd_agent(3)
    p6  = _prem_usd_agent(6)
    p12 = _prem_usd_agent(12)

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"3 شهور  — {p3}$",  callback_data="ag_prem_3")],
        [InlineKeyboardButton(f"6 شهور  — {p6}$",  callback_data="ag_prem_6")],
        [InlineKeyboardButton(f"12 شهر  — {p12}$", callback_data="ag_prem_12")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="agent_panel")],
    ])
    await q.edit_message_text(
        f"<b>{SEP}\n✅ بريميوم — سعر الوكيل\n{SEP}</b>\nاختر الباقة:",
        parse_mode="HTML",
        reply_markup=kb,
    )
    return AG_WAIT_PREM_UN


async def ag_prem_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if not _check_agent(uid):
        return await q.answer("🚫 غير مصرّح", show_alert=True)

    months   = int(q.data.split("_")[-1])
    usd      = _prem_usd_agent(months)
    label    = f"{months} {'شهر' if months == 12 else 'شهور'}"

    ctx.user_data["ag_buy"] = {"svc": "premium", "label": label, "months": months, "usd": usd}
    ctx.user_data["ag_bot_msg"] = {"chat_id": q.message.chat_id, "msg_id": q.message.message_id}

    await q.edit_message_text(
        f"<b>{SEP}\n✅ بريميوم — {label}\n{SEP2}</b>\n"
        f"💲 السعر: <b>{usd}$</b>\n\n"
        f"✏️ أرسل معرف الحساب:\n<code>@username</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="agent_panel")]
        ]),
    )
    return AG_WAIT_PREM_UN


async def ag_prem_recv_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not _check_agent(uid):
        return ConversationHandler.END

    raw      = update.message.text.strip().lstrip("@")
    buy      = ctx.user_data.get("ag_buy", {})
    usd      = buy.get("usd", 0.0)
    label    = buy.get("label", "")
    balance  = get_balance(uid)

    if balance < usd:
        await update.message.reply_text(
            f"⚠️ <b>رصيدك غير كافٍ</b>\n\n"
            f"رصيدك: <b>{balance:.4f}$</b>\n"
            f"المطلوب: <b>{usd:.4f}$</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ لوحة الوكيل", callback_data="agent_panel")]
            ]),
        )
        ctx.user_data.pop("ag_buy", None)
        return ConversationHandler.END

    ctx.user_data["ag_buy"]["username"] = raw

    await update.message.reply_text(
        f"<b>{SEP}\n✅ تأكيد الطلب\n{SEP2}</b>\n"
        f"📦 بريميوم {label}\n"
        f"👤 <code>@{raw}</code>\n"
        f"💲 <b>{usd}$</b>\n\n"
        f"هل تؤكد الطلب؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد", callback_data="ag_confirm"),
                InlineKeyboardButton("❌ إلغاء", callback_data="agent_panel"),
            ]
        ]),
    )
    return AG_WAIT_PREM_CONF


# ═══════════════════════════════════════════════════════════════
# 4.  تأكيد الطلب والتنفيذ
# ═══════════════════════════════════════════════════════════════

async def ag_confirm_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    if not _check_agent(uid):
        return await q.answer("🚫 غير مصرّح", show_alert=True)

    buy      = ctx.user_data.get("ag_buy", {})
    svc      = buy.get("svc", "")
    label    = buy.get("label", "")
    usd      = buy.get("usd", 0.0)
    username = buy.get("username", "")
    qty      = buy.get("qty", 0)
    months   = buy.get("months", 0)

    if not svc or not username:
        await q.edit_message_text("⚠️ بيانات الطلب غير مكتملة. أعد المحاولة.")
        ctx.user_data.pop("ag_buy", None)
        return ConversationHandler.END

    # ── فحص الرصيد مجدداً (تحقق مزدوج) ──
    balance = get_balance(uid)
    if balance < usd:
        await q.edit_message_text(
            f"⚠️ <b>رصيدك غير كافٍ</b>\n\nرصيدك: <b>{balance:.4f}$</b>\nالمطلوب: <b>{usd:.4f}$</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ لوحة الوكيل", callback_data="agent_panel")]
            ]),
        )
        ctx.user_data.pop("ag_buy", None)
        return ConversationHandler.END

    # ── خصم الرصيد وإنشاء الطلب ──
    deduct_balance(uid, usd, f"شراء وكيل: {label}")
    detail_str = f"[وكيل] {svc} {label} → @{username}"
    oid = create_order(uid, detail_str, username, usd)

    icon = "✅" if svc == "premium" else "⭐"
    buyer_tag = f"@{q.from_user.username}" if q.from_user.username else f"ID:{uid}"

    # ── توجيه نجوم/بريميوم للطابور التلقائي ──
    is_auto = svc in ("stars", "premium")
    if is_auto:
        from fragment_queue import fragment_queue
        _duration = ""
        if svc == "premium":
            _duration = str(months) if months else "3"

        add_fragment_order(
            order_id=oid, user_id=uid, svc=svc,
            username=username, label=label, amount_usd=usd,
            amount=qty if svc == "stars" else 0,
            duration=_duration,
        )
        await fragment_queue.put({
            "oid": oid, "user_id": uid, "svc": svc,
            "username": username, "label": label,
            "amount": qty if svc == "stars" else None,
            "duration": _duration or None,
        })
    else:
        kb_admin = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏳ جارٍ", callback_data=f"process_{oid}")],
            [
                InlineKeyboardButton("✅ تم",    callback_data=f"done_{oid}"),
                InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{oid}"),
            ],
        ])
        await ctx.bot.send_message(
            ADMIN_ID,
            f"{icon} <b>[وكيل] {svc} {label} — #{oid}</b>\n"
            f"👤 المشتري: {buyer_tag} (<code>{uid}</code>)\n"
            f"📲 إلى: <b>@{username}</b>\n"
            f"💲 {usd:.4f}$",
            reply_markup=kb_admin,
            parse_mode="HTML",
        )

    await asyncio.sleep(0.5)
    auto_note = (
        "⚡ <i>جاري التنفيذ التلقائي — ستتلقى إشعاراً فور الانتهاء</i>"
        if is_auto else "⏳ سيُنفَّذ خلال 0–24 ساعة"
    )
    await q.edit_message_text(
        f"<b>{SEP}\n{icon} تم استلام الطلب\n{SEP2}</b>\n"
        f"📦 <b>{label}</b>\n"
        f"👤 <code>@{username}</code>\n"
        f"💲 <b>{usd:.4f} $</b>\n"
        f"رقم الطلب: <b>#{oid}</b>\n{auto_note}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ لوحة الوكيل", callback_data="agent_panel")]
        ]),
    )
    ctx.user_data.pop("ag_buy", None)
    ctx.user_data.pop("ag_bot_msg", None)
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════
# 5.  إلغاء / fallback
# ═══════════════════════════════════════════════════════════════

async def ag_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("ag_buy", None)
    ctx.user_data.pop("ag_bot_msg", None)
    if update.message:
        await update.message.reply_text("❌ تم الإلغاء.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════════════════════
# تجميع الـ handlers
# ═══════════════════════════════════════════════════════════════

agent_panel_handler = CallbackQueryHandler(agent_panel_cb, pattern="^agent_panel$")

agent_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(ag_stars_menu,  pattern="^ag_buy_stars$"),
        CallbackQueryHandler(ag_prem_menu,   pattern="^ag_buy_prem$"),
    ],
    states={
        AG_WAIT_STARS_QTY: [
            CallbackQueryHandler(ag_stars_pick_qty,    pattern=r"^ag_stars_\d+$"),
            CallbackQueryHandler(ag_stars_custom_start, pattern="^ag_stars_custom$"),
        ],
        AG_WAIT_CUSTOM_QTY: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, ag_stars_custom_qty),
        ],
        AG_WAIT_STARS_UN: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, ag_stars_recv_username),
        ],
        AG_WAIT_STARS_CONF: [
            CallbackQueryHandler(ag_confirm_cb, pattern="^ag_confirm$"),
        ],
        AG_WAIT_PREM_UN: [
            CallbackQueryHandler(ag_prem_pick,          pattern=r"^ag_prem_\d+$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, ag_prem_recv_username),
        ],
        AG_WAIT_PREM_CONF: [
            CallbackQueryHandler(ag_confirm_cb, pattern="^ag_confirm$"),
        ],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, ag_cancel),
        CallbackQueryHandler(ag_cancel,        pattern="^agent_panel$"),
    ],
    per_message=False,
    allow_reentry=True,
)
