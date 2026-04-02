"""
قسم الألعاب — PUBG Mobile / PUBG New State / Free Fire
محادثة واحدة موحّدة تخدم كل الألعاب
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
)

from config import ADMIN_ID
from db import (
    get_user, get_balance, deduct_balance, is_banned,
    convert_from_usd, create_order, get_text,
    get_services, get_service_by_id, update_service_price,
)
from keyboards import make_btn as MB, admin_edit_row

SEP = "━━━━━━━━━━━━━━━━━━━━"

# ── حالات المحادثة ──────────────────────────────────────────────
GAME_WAIT_ID      = 30
GAME_WAIT_CONFIRM = 31
GAME_EDIT_PRICE   = 32

# ── بيانات العرض لكل فئة ─────────────────────────────────────────
GAME_META = {
    "pubg":     {"label": "PUBG Mobile 🔫",     "unit": "UC",   "back": "games"},
    "newstate": {"label": "PUBG New State 🆕",   "unit": "NC",   "back": "games"},
    "freefire": {"label": "Free Fire 💎",         "unit": "ماسة", "back": "games"},
}


# ═══════════════════════════════════════════════
# 1. قائمة الألعاب
# ═══════════════════════════════════════════════

async def games_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    rows = [
        [
            MB("PUBG Mobile 🔫",   "game_cat_pubg",     "btn_game_pubg"),
            MB("PUBG New State 🆕", "game_cat_newstate", "btn_game_newstate"),
        ],
        [
            MB("Free Fire 💎",      "game_cat_freefire", "btn_game_freefire"),
        ],
        [MB("🔙 رجوع", "general", "btn_games_back")],
    ]
    rows += admin_edit_row("games", uid)
    kb = InlineKeyboardMarkup(rows)

    heading = get_text("games_menu", "🎮 قسم الألعاب")
    await q.edit_message_text(
        f"<b>{SEP}\n{heading}\n{SEP}</b>\n\nاختر اللعبة:",
        reply_markup=kb,
        parse_mode="HTML",
    )


# ═══════════════════════════════════════════════
# 2. قائمة باقات اللعبة
# ═══════════════════════════════════════════════

async def game_packages(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    # game_cat_pubg  →  "pubg"
    category = q.data.replace("game_cat_", "")
    meta = GAME_META.get(category)
    if not meta:
        return await q.answer("⚠️ لعبة غير معروفة", show_alert=True)

    user = get_user(q.from_user.id)
    currency = user[3]

    services = get_services(category)
    if not services:
        return await q.edit_message_text(
            "⚠️ لا توجد باقات متاحة حالياً.",
            reply_markup=InlineKeyboardMarkup(
                [[MB("🔙 رجوع", "games", "btn_games_pkg_back")]]
            ),
        )

    buttons = []
    for sid, name, value, usd in services:
        price_display = convert_from_usd(usd, currency)
        label = f"{value} {meta['unit']}  —  {price_display:.2f} {currency}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"gpkg_{sid}"),
        ])

    buttons.append([MB("🔙 رجوع", "games", "btn_games_pkg_back")])

    await q.edit_message_text(
        f"<b>{SEP}\n{meta['label']}\n{SEP}</b>\n\nاختر الباقة:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# 3. اختيار باقة → طلب ID
# ═══════════════════════════════════════════════

async def game_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    sid = int(q.data.split("_")[1])
    row = get_service_by_id(sid)
    if not row:
        return await q.answer("⚠️ الباقة غير موجودة", show_alert=True)

    _id, category, name, value, price_usd = row
    meta = GAME_META.get(category, {"label": category, "unit": ""})

    user = get_user(q.from_user.id)
    currency = user[3]
    price_display = convert_from_usd(price_usd, currency)

    ctx.user_data["game_sid"]       = sid
    ctx.user_data["game_category"]  = category
    ctx.user_data["game_label"]     = meta["label"]
    ctx.user_data["game_unit"]      = meta["unit"]
    ctx.user_data["game_value"]     = value
    ctx.user_data["game_price_usd"] = price_usd
    ctx.user_data["game_price_dis"] = price_display
    ctx.user_data["game_currency"]  = currency
    ctx.user_data["game_step"]      = "wait_id"

    await q.edit_message_text(
        f"<b>{SEP}\n{meta['label']}\n{SEP}</b>\n\n"
        f"الباقة المختارة: <b>{value} {meta['unit']}</b>\n"
        f"السعر: <b>{price_display:.2f} {currency}</b>\n\n"
        "📩 أرسل <b>ID الحساب</b> في اللعبة:",
        parse_mode="HTML",
    )
    return GAME_WAIT_ID


# ═══════════════════════════════════════════════
# 4. استقبال ID → عرض التأكيد
# ═══════════════════════════════════════════════

async def game_recv_id(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if ctx.user_data.get("game_step") != "wait_id":
        return ConversationHandler.END

    game_id = update.message.text.strip()
    ctx.user_data["game_id"]   = game_id
    ctx.user_data["game_step"] = "confirm"

    value    = ctx.user_data["game_value"]
    unit     = ctx.user_data["game_unit"]
    label    = ctx.user_data["game_label"]
    price    = ctx.user_data["game_price_dis"]
    currency = ctx.user_data["game_currency"]

    await update.message.reply_text(
        f"<b>{SEP}\n📋 تأكيد الطلب\n{SEP}</b>\n\n"
        f"🎮 اللعبة: <b>{label}</b>\n"
        f"💎 الكمية: <b>{value} {unit}</b>\n"
        f"🆔 ID: <code>{game_id}</code>\n"
        f"💰 السعر: <b>{price:.2f} {currency}</b>\n\n"
        "هل تريد تأكيد الطلب؟",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تأكيد",  callback_data="game_ok"),
                InlineKeyboardButton("❌ إلغاء", callback_data="game_cancel"),
            ]
        ]),
        parse_mode="HTML",
    )
    return GAME_WAIT_CONFIRM


# ═══════════════════════════════════════════════
# 5. تأكيد / إلغاء الطلب
# ═══════════════════════════════════════════════

async def game_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "game_cancel":
        ctx.user_data.clear()
        await q.message.reply_text(
            "❌ تم إلغاء الطلب.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")]]
            ),
        )
        return ConversationHandler.END

    uid      = q.from_user.id
    user     = get_user(uid)
    balance  = get_balance(uid)
    price_usd = ctx.user_data["game_price_usd"]

    if balance < price_usd:
        shortage = convert_from_usd(price_usd - balance, ctx.user_data["game_currency"])
        await q.message.reply_text(
            f"⚠️ رصيدك غير كافٍ.\n"
            f"ينقصك: <b>{shortage:.2f} {ctx.user_data['game_currency']}</b>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 شحن الرصيد", callback_data="deposit")],
                [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")],
            ]),
            parse_mode="HTML",
        )
        ctx.user_data.clear()
        return ConversationHandler.END

    label   = ctx.user_data["game_label"]
    deduct_balance(uid, price_usd, f"شراء: شحن ألعاب {label}")
    value   = ctx.user_data["game_value"]
    unit    = ctx.user_data["game_unit"]
    game_id = ctx.user_data["game_id"]
    price_dis = ctx.user_data["game_price_dis"]
    currency  = ctx.user_data["game_currency"]

    order_id = create_order(
        uid,
        label,
        f"{game_id} | {value} {unit}",
        price_usd,
    )

    await q.message.reply_text(
        f"<b>✅ تم إنشاء الطلب بنجاح!</b>\n\n"
        f"رقم الطلب: <b>#{order_id}</b>\n"
        f"اللعبة: {label}\n"
        f"الكمية: {value} {unit}\n"
        f"ID: <code>{game_id}</code>\n"
        f"المبلغ: {price_dis:.2f} {currency}\n\n"
        "سيتم التنفيذ خلال وقت قصير ✨",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📦 طلباتي", callback_data="orders")],
            [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main_menu")],
        ]),
        parse_mode="HTML",
    )

    # إشعار الأدمن
    new_balance = get_balance(uid)
    username = q.from_user.username or "—"
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🎮 <b>طلب لعبة جديد #{order_id}</b>\n\n"
            f"المستخدم: @{username} (<code>{uid}</code>)\n"
            f"اللعبة: {label}\n"
            f"الكمية: {value} {unit}\n"
            f"ID اللعبة: <code>{game_id}</code>\n"
            f"المبلغ: {price_dis:.2f} {currency} (${price_usd:.2f})\n"
            f"رصيد بعد الخصم: ${new_balance:.2f}",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ تنفيذ",  callback_data=f"order_done_{order_id}"),
                    InlineKeyboardButton("❌ إلغاء",  callback_data=f"order_cancel_{order_id}"),
                ]
            ]),
            parse_mode="HTML",
        )
    except Exception:
        pass

    ctx.user_data.clear()
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# 6. الأدمن — إدارة أسعار الألعاب
# ═══════════════════════════════════════════════

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


async def admin_games_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("PUBG Mobile 🔫",   callback_data="admin_gcat_pubg"),
            InlineKeyboardButton("PUBG New State 🆕", callback_data="admin_gcat_newstate"),
        ],
        [
            InlineKeyboardButton("Free Fire 💎",      callback_data="admin_gcat_freefire"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
    ])

    await q.edit_message_text(
        f"<b>🎮 إدارة أسعار الألعاب</b>\n\nاختر اللعبة:",
        reply_markup=kb,
        parse_mode="HTML",
    )


async def admin_game_cat_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()

    category = q.data.replace("admin_gcat_", "")
    meta = GAME_META.get(category, {"label": category, "unit": ""})
    services = get_services(category)

    if not services:
        return await q.edit_message_text(
            "⚠️ لا توجد باقات.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 رجوع", callback_data="admin_games")]]
            ),
        )

    buttons = []
    for sid, name, value, usd in services:
        label = f"{value} {meta['unit']}  ←  ${usd:.2f}"
        buttons.append([
            InlineKeyboardButton(label, callback_data=f"admin_gedit_{sid}"),
        ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_games")])

    await q.edit_message_text(
        f"<b>{meta['label']}</b>\n\nاضغط على الباقة لتعديل سعرها:",
        reply_markup=InlineKeyboardMarkup(buttons),
        parse_mode="HTML",
    )


async def admin_game_edit_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()

    sid = int(q.data.replace("admin_gedit_", ""))
    row = get_service_by_id(sid)
    if not row:
        return await q.answer("⚠️ الباقة غير موجودة", show_alert=True)

    _id, category, name, value, price_usd = row
    meta = GAME_META.get(category, {"label": category, "unit": ""})

    ctx.user_data["gadmin_sid"]      = sid
    ctx.user_data["gadmin_category"] = category
    ctx.user_data["gadmin_label"]    = f"{value} {meta['unit']}"

    await q.message.reply_text(
        f"<b>✏️ تعديل سعر</b>\n\n"
        f"اللعبة: {meta['label']}\n"
        f"الباقة: <b>{value} {meta['unit']}</b>\n"
        f"السعر الحالي: <b>${price_usd:.2f}</b>\n\n"
        "أرسل السعر الجديد بالدولار (مثال: 1.50):",
        parse_mode="HTML",
    )
    return GAME_EDIT_PRICE


async def admin_game_save_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    if "gadmin_sid" not in ctx.user_data:
        return ConversationHandler.END

    try:
        new_price = float(update.message.text.strip())
        if new_price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا صحيحًا أكبر من صفر.")
        return GAME_EDIT_PRICE

    sid   = ctx.user_data.pop("gadmin_sid")
    cat   = ctx.user_data.pop("gadmin_category")
    label = ctx.user_data.pop("gadmin_label")

    update_service_price(sid, new_price)

    await update.message.reply_text(
        f"✅ تم تحديث السعر\n\n"
        f"الباقة: <b>{label}</b>\n"
        f"السعر الجديد: <b>${new_price:.2f}</b>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع للألعاب", callback_data=f"admin_gcat_{cat}")],
        ]),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def admin_game_edit_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.pop("gadmin_sid", None)
    ctx.user_data.pop("gadmin_category", None)
    ctx.user_data.pop("gadmin_label", None)
    if update.callback_query:
        await update.callback_query.answer("إلغاء")
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# 7. ConversationHandlers للتسجيل في bot.py
# ═══════════════════════════════════════════════

# محادثة الشراء (للمستخدمين)
game_buy_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(game_select, pattern=r"^gpkg_\d+$"),
    ],
    states={
        GAME_WAIT_ID: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, game_recv_id),
        ],
        GAME_WAIT_CONFIRM: [
            CallbackQueryHandler(game_confirm, pattern=r"^game_(ok|cancel)$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(games_menu, pattern="^games$"),
    ],
    allow_reentry=True,
    name="game_buy",
    persistent=False,
)

# محادثة تعديل الأسعار (للأدمن)
game_admin_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(admin_game_edit_start, pattern=r"^admin_gedit_\d+$"),
    ],
    states={
        GAME_EDIT_PRICE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_game_save_price),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(admin_game_edit_cancel, pattern="^admin_games$"),
    ],
    allow_reentry=True,
    name="game_admin_edit",
    persistent=False,
)
