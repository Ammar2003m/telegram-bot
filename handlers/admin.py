import logging

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters,
    ApplicationHandlerStop,
)

log = logging.getLogger(__name__)

from config import ADMIN_ID, DB
from db import (
    get_user, update_balance, add_balance, remove_balance, deduct_balance, toggle_ban,
    get_rate, update_rate, get_all_rates, get_stats, get_rich_stats, get_all_user_ids,
    add_username_db, get_usernames, delete_username_db,
    add_coupon, get_coupons, delete_coupon,
    update_order_status, get_order,
    get_price, update_price, get_all_prices,
    get_text, update_text, get_all_texts,
    add_word, get_all_words, delete_word, search_words, replace_words_html,
    is_maintenance, set_str_setting, get_popular_services,
    is_agent_user, set_agent_status, get_agents,
    get_agent_price, set_agent_price, get_all_agent_prices, delete_agent_price,
    get_ref_percent, set_ref_percent,
    get_card_rate, set_card_rate, get_all_risk_scores, reset_risk,
    get_withdrawal, update_withdrawal,
    deduct_card_balance, get_total_card_balance,
    get_order_group, set_order_group,
    get_user_statement, get_transactions,
    is_review_dismissed, dismiss_review,
    get_top_spenders,
)
from keyboards import admin_panel, back, make_btn as MB, make_url_btn as MU

# ── حالات المحادثة ──────────────────────────────
(
    ADM_UID, ADM_AMT,
    BAN_UID,
    EDIT_RATE, EDIT_RATE_VAL,
    FIND_UID,
    BC_MSG,
    AU_NAME, AU_TYPE, AU_PRICE,
    CP_CODE, CP_DISC, CP_LIMIT,
    ADM_ACT,
) = range(14)

EDIT_UI_VAL       = 14
WW_OLD            = 15
WW_NEW            = 16
WW_SEARCH         = 17
WW_DEL            = 18
ADM_REASON        = 19
WD_REJECT_REASON  = 20
ADMIN_STMT        = 31


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


# ── أوامر ────────────────────────────────────────

async def cmd_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("👑 <b>لوحة تحكم المالك</b>", reply_markup=admin_panel(), parse_mode="HTML")


async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    u, o = get_stats()
    await update.message.reply_text(f"📊 المستخدمون: <b>{u}</b> | الطلبات: <b>{o}</b>", parse_mode="HTML")


async def cmd_add_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    try:
        uid, amt = int(ctx.args[0]), float(ctx.args[1])
        add_balance(uid, amt, "شحن أدمن /add_balance", "إيداع")
        await update.message.reply_text(f"✅ تم شحن <b>{amt}$</b> لـ <code>{uid}</code>", parse_mode="HTML")
    except Exception:
        await update.message.reply_text("❌ الصيغة: /add_balance ID AMOUNT")


# ── لوحة التحكم (callback) ──────────────────────

async def admin_panel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.edit_message_text("👑 <b>لوحة تحكم المالك</b>", reply_markup=admin_panel(), parse_mode="HTML")


# ── تنفيذ/إلغاء الطلبات ─────────────────────────

async def done_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    oid   = int(q.data.split("_")[1])
    order = get_order(oid)
    update_order_status(oid, "completed")
    await q.edit_message_text(
        q.message.text + "\n\n✅ <b>تم التنفيذ</b>",
        parse_mode="HTML",
    )
    if order:
        uid = order["user_id"]
        try:
            await ctx.bot.send_message(
                uid,
                f"✅ تم تنفيذ طلبك رقم <b>#{oid}</b> بنجاح! ✨",
                parse_mode="HTML",
            )
        except Exception:
            pass
        if not is_review_dismissed(uid):
            try:
                await ctx.bot.send_message(
                    uid,
                    "⭐ لا تنسَ تقييم خدمتنا ومشاركة تجربتك مع الآخرين!",
                    reply_markup=InlineKeyboardMarkup([
                        [MU("✍️ قيّمنا هنا", "https://t.me/KKGG5/415", "btn_review_rate")],
                        [MB("🔕 لا تذكرني", "review_dismiss", "btn_review_dismiss")],
                    ]),
                )
            except Exception:
                pass
    await q.answer("تم التنفيذ ✅")


async def process_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يتم المعالجة — يُشعر العميل ويُحدّث الحالة."""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    oid   = int(q.data.split("_")[1])
    order = get_order(oid)
    update_order_status(oid, "processing")
    await q.edit_message_text(
        q.message.text + "\n\n⏳ <b>قيد المعالجة</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ تم",   callback_data=f"done_{oid}"),
            InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{oid}"),
        ]]),
    )
    if order:
        try:
            await ctx.bot.send_message(
                order["user_id"],
                f"⏳ طلبك رقم <b>#{oid}</b> الآن قيد المعالجة، سيُنفَّذ قريباً.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    await q.answer("⏳ جارٍ المعالجة")


async def cancel_order(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    oid   = int(q.data.split("_")[1])
    order = get_order(oid)
    update_order_status(oid, "cancelled")
    if order:
        add_balance(order["user_id"], order["amount"], f"استرداد إلغاء طلب #{oid}", "استرداد")
        try:
            await ctx.bot.send_message(
                order["user_id"],
                f"❌ تم إلغاء طلبك رقم <b>#{oid}</b> واسترداد المبلغ إلى رصيدك.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    await q.edit_message_text(
        q.message.text + "\n\n❌ <b>تم الإلغاء وإرجاع الرصيد</b>",
        parse_mode="HTML",
    )
    await q.answer("تم الإلغاء ❌")


# ── إدارة العملات ────────────────────────────────

async def admin_currency_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    rates = get_all_rates()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"YER = {rates.get('YER', 550)}", callback_data="editrate_YER")],
        [InlineKeyboardButton(f"SAR = {rates.get('SAR', 3.75)}", callback_data="editrate_SAR")],
        [InlineKeyboardButton(f"EGP = {rates.get('EGP', 50)}", callback_data="editrate_EGP")],
        [InlineKeyboardButton(f"USDT = {rates.get('USDT', 1)}", callback_data="editrate_USDT")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
    ])
    await q.edit_message_text("💱 <b>إدارة العملات</b>", reply_markup=kb, parse_mode="HTML")


async def start_edit_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    currency = q.data.split("_")[1]
    ctx.user_data["edit_currency"] = currency
    await q.message.reply_text(f"✏️ أدخل سعر <b>{currency}</b> الجديد (وحدات لكل 1$):", parse_mode="HTML")
    return EDIT_RATE_VAL


async def save_rate(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        value    = float(update.message.text.strip())
        currency = ctx.user_data.get("edit_currency", "")
        update_rate(currency, value)
        await update.message.reply_text(f"✅ تم تحديث <b>{currency}</b> → <b>{value}</b>", parse_mode="HTML")
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا.")
    ctx.user_data.pop("edit_currency", None)
    return ConversationHandler.END


# ── إدارة المستخدمين ─────────────────────────────

async def admin_users_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    u, o = get_stats()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات",    callback_data="admin_stats")],
        [InlineKeyboardButton("🔍 بحث مستخدم",    callback_data="admin_find")],
        [InlineKeyboardButton("🚫 حظر",            callback_data="admin_ban")],
        [InlineKeyboardButton("✅ رفع حظر",        callback_data="admin_unban")],
        [InlineKeyboardButton("🔙 رجوع",           callback_data="admin_panel")],
    ])
    await q.edit_message_text(
        f"👤 <b>المستخدمون</b>\n\n📊 الإجمالي: <b>{u}</b> | الطلبات: <b>{o}</b>",
        reply_markup=kb, parse_mode="HTML"
    )


async def admin_stats_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    s = get_rich_stats()
    popular = get_popular_services(5)
    pop_lines = ""
    if popular:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        pop_lines = "\n\n🔥 <b>الأكثر طلباً:</b>\n" + "\n".join(
            f"{medals[i]} {r['service']} ({r['total']})" for i, r in enumerate(popular)
        )

    msg = (
        f"📊 <b>إحصائيات المتجر</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👥 المستخدمون: <b>{s['users']}</b>\n"
        f"📦 إجمالي الطلبات: <b>{s['orders']}</b>\n"
        f"⏳ معلّقة: <b>{s['pending']}</b>  |  ✅ مكتملة: <b>{s['done']}</b>  |  ❌ ملغية: <b>{s['cancelled']}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📅 طلبات اليوم: <b>{s['today']}</b>\n"
        f"💰 إيرادات اليوم: <b>{s['today_rev']:.2f}$</b>\n"
        f"💵 إجمالي الإيرادات: <b>{s['revenue']:.2f}$</b>"
        f"{pop_lines}"
    )
    await q.edit_message_text(msg, reply_markup=back("admin_panel"), parse_mode="HTML")


async def start_find(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    ctx.user_data["find_action"] = "info"
    await q.message.reply_text("🔍 أدخل ID المستخدم:")
    return FIND_UID


async def start_ban(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    ctx.user_data["find_action"] = "ban" if q.data == "admin_ban" else "unban"
    await q.message.reply_text("🔍 أدخل ID المستخدم:")
    return FIND_UID


async def process_find_user(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        uid  = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا.")
        return FIND_UID

    action = ctx.user_data.pop("find_action", "info")
    user   = get_user(uid)

    if not user:
        await update.message.reply_text("❌ المستخدم غير موجود.")
        return ConversationHandler.END

    if action == "ban":
        toggle_ban(uid, 1)
        await update.message.reply_text(f"🚫 تم حظر <code>{uid}</code>", parse_mode="HTML")
    elif action == "unban":
        toggle_ban(uid, 0)
        await update.message.reply_text(f"✅ تم رفع حظر <code>{uid}</code>", parse_mode="HTML")
    else:
        banned = "🚫 محظور" if user["is_banned"] else "✅ نشط"
        await update.message.reply_text(
            f"👤 <b>معلومات المستخدم</b>\n\n"
            f"🆔 <code>{user['user_id']}</code>\n"
            f"📛 @{user['username'] or '—'}\n"
            f"💰 {user['balance']:.4f}$\n"
            f"💱 {user['currency']}\n"
            f"🏴 {banned}",
            parse_mode="HTML"
        )
    return ConversationHandler.END


# ── شحن يدوي ────────────────────────────────────

async def start_add_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.message.reply_text("💰 أدخل ID المستخدم:")
    return ADM_UID


async def get_balance_uid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا صحيحًا.")
        return ADM_UID

    user = get_user(uid)
    if not user:
        await update.message.reply_text("❌ المستخدم غير موجود في قاعدة البيانات.")
        return ADM_UID

    ctx.user_data["adm_uid"] = uid
    bal = user["balance"]
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة رصيد", callback_data=f"adm_add_{uid}"),
            InlineKeyboardButton("➖ خصم من رصيد", callback_data=f"adm_ded_{uid}"),
        ]
    ])
    await update.message.reply_text(
        f"👤 المستخدم: <code>{uid}</code>\n"
        f"💰 الرصيد الحالي: <b>{bal:.4f}$</b>\n\n"
        f"اختر الإجراء:",
        reply_markup=kb,
        parse_mode="HTML",
    )
    return ADM_ACT


async def pick_adm_action(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.answer()
    action = "add" if q.data.startswith("adm_add_") else "deduct"
    try:
        uid = int(q.data.split("_")[-1])
    except Exception:
        return ConversationHandler.END
    ctx.user_data["adm_uid"]    = uid
    ctx.user_data["adm_action"] = action
    label = "➕ إضافة" if action == "add" else "➖ خصم"
    await q.message.reply_text(f"{label}: أدخل المبلغ بالدولار:")
    return ADM_AMT


async def do_add_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا صحيحًا.")
        return ADM_AMT

    uid    = ctx.user_data.get("adm_uid")
    action = ctx.user_data.get("adm_action", "add")

    if action == "deduct":
        ctx.user_data["adm_deduct_amt"] = amount
        await update.message.reply_text(
            f"📝 أدخل سبب خصم <b>{amount}$</b> من <code>{uid}</code>:\n(سيتم إرساله للعميل)",
            parse_mode="HTML"
        )
        return ADM_REASON
    else:
        ctx.user_data.pop("adm_uid", None)
        ctx.user_data.pop("adm_action", None)
        add_balance(uid, amount, "شحن يدوي من الأدمن", "إيداع")
        await update.message.reply_text(
            f"✅ تم شحن <b>{amount}$</b> لـ <code>{uid}</code>", parse_mode="HTML"
        )
        try:
            await ctx.bot.send_message(uid, f"✅ تم شحن رصيدك بمبلغ <b>{amount}$</b> 🎉", parse_mode="HTML")
        except Exception:
            pass
        return ConversationHandler.END

    return ConversationHandler.END


async def do_deduct_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    reason = update.message.text.strip()
    uid    = ctx.user_data.pop("adm_uid", None)
    amount = ctx.user_data.pop("adm_deduct_amt", 0)
    ctx.user_data.pop("adm_action", None)
    if not uid or not amount:
        return ConversationHandler.END
    remove_balance(uid, amount, f"خصم يدوي من الأدمن: {reason}", "خصم")
    await update.message.reply_text(
        f"✅ تم خصم <b>{amount}$</b> من <code>{uid}</code>\nالسبب: {reason}", parse_mode="HTML"
    )
    try:
        await ctx.bot.send_message(
            uid,
            f"ℹ️ <b>تنبيه: تم خصم <b>{amount}$</b> من رصيدك.</b>\n📝 السبب: {reason}",
            parse_mode="HTML"
        )
    except Exception:
        pass
    return ConversationHandler.END


async def review_dismiss_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("تم! لن نُذكّرك مجدداً.")
    dismiss_review(q.from_user.id)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass




# ── الطلبات ──────────────────────────────────────

async def admin_orders_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    import sqlite3
    with sqlite3.connect(DB) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            "SELECT * FROM orders WHERE status='pending' ORDER BY id DESC LIMIT 15"
        ).fetchall()

    if not rows:
        await q.edit_message_text("📦 لا يوجد طلبات معلقة.", reply_markup=back("admin_panel"))
        return

    for o in rows:
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ تم",             callback_data=f"done_{o['id']}"),
                InlineKeyboardButton("❌ إلغاء",          callback_data=f"cancel_{o['id']}"),
            ],
            [
                InlineKeyboardButton("⏳ يتم المعالجة",   callback_data=f"process_{o['id']}"),
            ],
        ])
        await ctx.bot.send_message(
            q.from_user.id,
            f"📦 <b>#{o['id']}</b> | 👤 <code>{o['user_id']}</code>\n"
            f"⚙️ {o['service']}\n📝 {o['details']}\n💲 {o['amount']}$",
            reply_markup=kb, parse_mode="HTML"
        )


# ── الإذاعة ──────────────────────────────────────

async def start_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.message.reply_text("📢 أرسل الرسالة للإذاعة:")
    return BC_MSG


async def do_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    users   = get_all_user_ids()
    success = 0
    for uid in users:
        try:
            await ctx.bot.copy_message(uid, update.chat.id if hasattr(update, "chat") else update.message.chat_id, update.message.message_id)
            success += 1
        except Exception:
            pass
    await update.message.reply_text(f"✅ تم إرسال الإذاعة لـ <b>{success}/{len(users)}</b>", parse_mode="HTML")
    return ConversationHandler.END


async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text("📢 أرسل الرسالة:")
    return BC_MSG


# ── اليوزرات ─────────────────────────────────────

async def admin_usernames_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة",   callback_data="add_username")],
        [InlineKeyboardButton("📋 عرض",     callback_data="list_usernames")],
        [InlineKeyboardButton("🔙 رجوع",    callback_data="admin_panel")],
    ])
    await q.edit_message_text("🏷 <b>اليوزرات</b>", reply_markup=kb, parse_mode="HTML")


async def start_add_username(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.message.reply_text("✏️ أدخل اليوزر (بدون @):")
    return AU_NAME


async def au_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["au_name"] = update.message.text.strip().lstrip("@")
    await update.message.reply_text(
        "📂 اختر نوع اليوزر:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🌐 منصة (NFT)",  callback_data="autype_nft"),
                InlineKeyboardButton("👤 ملكية",        callback_data="autype_normal"),
            ]
        ]),
    )
    return AU_TYPE


async def au_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ctx.user_data["au_type"] = "NFT" if q.data == "autype_nft" else "ملكية"
    await q.message.reply_text("💲 السعر بالدولار:")
    return AU_PRICE


async def au_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا.")
        return AU_PRICE
    add_username_db(ctx.user_data.pop("au_name"), ctx.user_data.pop("au_type"), price)
    await update.message.reply_text("✅ تمت الإضافة.")
    return ConversationHandler.END


async def list_usernames_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    rows = get_usernames()
    if not rows:
        await q.edit_message_text("لا يوجد يوزرات.", reply_markup=back("admin_usernames"))
        return
    type_icon = {"NFT": "🌐", "ملكية": "👤"}
    kb_rows = []
    for r in rows:
        t_icon = type_icon.get(r["type"], "📂") if r["type"] else "📂"
        kb_rows.append([InlineKeyboardButton(
            f"🗑 @{r['username']}  {t_icon}{r['type'] or '—'}  ({r['price']}$)",
            callback_data=f"deluname_{r['id']}"
        )])
    kb_rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_usernames")])
    await q.edit_message_text("📋 <b>اليوزرات</b> (اضغط على أي يوزر للحذف):", reply_markup=InlineKeyboardMarkup(kb_rows), parse_mode="HTML")


async def del_username_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    delete_username_db(int(q.data.split("_")[1]))
    await q.answer("✅ تم الحذف", show_alert=True)
    await list_usernames_cb(update, ctx)


# ── الكوبونات ─────────────────────────────────────

async def admin_coupons_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    count = len(get_coupons())
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة",   callback_data="add_coupon")],
        [InlineKeyboardButton("📋 عرض",     callback_data="list_coupons")],
        [InlineKeyboardButton("🔙 رجوع",    callback_data="admin_panel")],
    ])
    await q.edit_message_text(f"🎟 <b>الكوبونات</b> ({count})", reply_markup=kb, parse_mode="HTML")


async def start_add_coupon(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.message.reply_text("🎟 أدخل كود الكوبون:")
    return CP_CODE


async def cp_code(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["cp_code"] = update.message.text.strip().upper()
    await update.message.reply_text("💯 نسبة الخصم (مثال: 10):")
    return CP_DISC


async def cp_disc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        d = float(update.message.text.strip())
        if not 0 < d <= 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أدخل نسبة بين 1-100.")
        return CP_DISC
    ctx.user_data["cp_disc"] = d
    await update.message.reply_text("🔢 عدد مرات الاستخدام:")
    return CP_LIMIT


async def cp_limit(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        limit = int(update.message.text.strip())
        if limit < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا.")
        return CP_LIMIT
    code = ctx.user_data.pop("cp_code")
    disc = ctx.user_data.pop("cp_disc")
    add_coupon(code, disc, limit)
    await update.message.reply_text(f"✅ كوبون <b>{code}</b> | خصم: <b>{disc}%</b> | الحد: <b>{limit}×</b>", parse_mode="HTML")
    return ConversationHandler.END


async def list_coupons_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    coupons = get_coupons()
    if not coupons:
        await q.edit_message_text("لا يوجد كوبونات.", reply_markup=back("admin_coupons"))
        return
    rows = []
    for c in coupons:
        icon = "✅" if c["is_active"] else "❌"
        rows.append([InlineKeyboardButton(
            f"{icon} {c['code']} — {c['discount']}% ({c['used_count']}/{c['usage_limit']})",
            callback_data=f"delcoupon_{c['code']}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_coupons")])
    await q.edit_message_text("📋 <b>الكوبونات</b> (اضغط للحذف):", reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")


async def del_coupon_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    code = "_".join(q.data.split("_")[1:])
    delete_coupon(code)
    await q.answer(f"✅ تم حذف {code}", show_alert=True)
    await list_coupons_cb(update, ctx)


# ── إدارة الأسعار ─────────────────────────────────

EDIT_PRICE_VAL = 20   # حالة جديدة خاصة بالأسعار

PRICE_LABELS = {
    # ── تيليجرام مميز ──
    "prem_3m":      "✅ تيليجرام مميز — 3 شهور",
    "prem_6m":      "✅ تيليجرام مميز — 6 شهور",
    "prem_12m":     "✅ تيليجرام مميز — 12 شهر",
    # ── نجوم وتفاعلات ──
    "stars_100":    "⭐ النجوم (أقل 1000) — سعر/100",
    "stars_1000":   "⭐ النجوم (1000+) — سعر/100",
    "like_1000":    "👍 التفاعلات — سعر/1000",
    # ── مشاهدات وتعزيزات ──
    "view_1":       "👁 مشاهدات منشور واحد — سعر/1000",
    "view_10":      "👁 مشاهدات آخر 10 — سعر/1000",
    "view_20":      "👁 مشاهدات آخر 20 — سعر/1000",
    "view_30":      "👁 مشاهدات آخر 30 — سعر/1000",
    "boost_10":     "⚡ التعزيزات — سعر/10",
    # ── أعضاء ونقل ──
    "member_90":    "👥 أعضاء ضمان 90  يوم — سعر/1000",
    "member_180":   "👥 أعضاء ضمان 180 يوم — سعر/1000",
    "member_365":   "👥 أعضاء ضمان 365 يوم — سعر/1000",
    "transfer_1000":"🔄 نقل أعضاء — سعر/1000",
    # ── نتفلكس ──
    "net_basic":    "🍿 نتفلكس الأساسية",
    "net_standard": "🍿 نتفلكس القياسية",
    "net_premium":  "🍿 نتفلكس المميزة",
    # ── راش ──
    "rush_price":   "🚀 راش Rush — السعر",
}


async def admin_prices_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await _show_prices_kb(update.message)


async def show_prices_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await _show_prices_kb(q.message, edit=True)


async def _show_prices_kb(msg, edit=False):
    prices = get_all_prices()
    rows   = []
    for key, label in PRICE_LABELS.items():
        cur = prices.get(key, 0)
        rows.append([InlineKeyboardButton(
            f"{label}: {cur}$", callback_data=f"editp_{key}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    kb   = InlineKeyboardMarkup(rows)
    text = "━━━━━━━━━━━━━━━\n💲 إدارة الأسعار\n━━━━━━━━━━━━━━━\nاضغط على السعر لتعديله:"
    if edit:
        await msg.edit_text(text, reply_markup=kb)
    else:
        await msg.reply_text(text, reply_markup=kb)


async def start_edit_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    service = q.data[len("editp_"):]
    label   = PRICE_LABELS.get(service, service)
    cur     = get_price(service)
    ctx.user_data["edit_price_service"] = service
    await q.message.reply_text(
        f"✏️ <b>{label}</b>\n"
        f"السعر الحالي: <b>{cur}$</b>\n\n"
        f"أدخل السعر الجديد بالدولار:",
        parse_mode="HTML"
    )
    return EDIT_PRICE_VAL


async def save_price_val(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    service = ctx.user_data.pop("edit_price_service", None)
    if not service:
        return ConversationHandler.END
    try:
        new_price = float(update.message.text.strip())
        if new_price < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا صحيحًا أكبر من 0.")
        return EDIT_PRICE_VAL

    update_price(service, new_price)
    label = PRICE_LABELS.get(service, service)
    await update.message.reply_text(
        f"✅ تم تحديث <b>{label}</b> → <b>{new_price}$</b>",
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def cancel_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data.clear()
    await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# محرّر الواجهة الديناميكي
# ═══════════════════════════════════════════════

UI_LABELS = {
    "welcome":           "رسالة الترحيب (start)",
    "main_menu":         "عنوان القائمة الرئيسية",
    "services_menu":     "عنوان قائمة الخدمات",
    "telegram_services": "عنوان خدمات تيليجرام",
    "general_menu":      "عنوان الخدمات العامة",
}


async def admin_ui_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض قائمة اختيار النص المراد تعديله"""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    texts = {row["key"]: row["text"] for row in get_all_texts()}
    rows  = []
    for key, label in UI_LABELS.items():
        rows.append([InlineKeyboardButton(
            f"✏️ {label}",
            callback_data=f"editui_{key}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])

    # عرض النصوص الحالية
    lines = ["🖊 <b>محرّر الواجهة</b>\n"]
    for key, label in UI_LABELS.items():
        val = texts.get(key, "—")
        lines.append(f"<b>{label}:</b>\n<code>{val}</code>\n")

    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML"
    )


async def start_edit_ui(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 1: اختيار المفتاح → طلب النص الجديد"""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    key   = q.data.replace("editui_", "")
    label = UI_LABELS.get(key, key)
    cur   = get_text(key)
    ctx.user_data["edit_ui_key"] = key

    await q.edit_message_text(
        f"🖊 <b>تعديل: {label}</b>\n\n"
        f"النص الحالي:\n<code>{cur}</code>\n\n"
        f"✏️ أرسل النص الجديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_ui")]
        ]),
        parse_mode="HTML"
    )
    return EDIT_UI_VAL


async def save_ui_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: حفظ النص الجديد"""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    key      = ctx.user_data.pop("edit_ui_key", None)
    new_text = update.message.text

    if not key:
        return ConversationHandler.END

    update_text(key, new_text)
    label = UI_LABELS.get(key, key)

    try:
        await update.message.delete()
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ تم تحديث <b>{label}</b>:\n<code>{new_text}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")]
        ])
    )
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# نظام استبدال الكلمات العالمي
# ═══════════════════════════════════════════════

def _words_kb(words: list, extra_cb: str = "admin_words") -> InlineKeyboardMarkup:
    """لوحة مفاتيح قائمة الكلمات مع أزرار حذف.
    نجرّد وسوم HTML من الكلمة الجديدة لأن أزرار تيليجرام لا تدعم HTML."""
    import re as _re
    rows = []
    for w in words:
        old_short = w["old"][:20] + "…" if len(w["old"]) > 20 else w["old"]
        new_plain = _re.sub(r"<[^>]+>", "", w["new"])   # إزالة HTML → إيموجي احتياطي
        new_short = new_plain[:20] + "…" if len(new_plain) > 20 else new_plain
        rows.append([InlineKeyboardButton(
            f"🗑 {old_short} → {new_short}",
            callback_data=f"delword_{w['old'][:30]}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=extra_cb)])
    return InlineKeyboardMarkup(rows)


async def admin_words_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """القائمة الرئيسية لإدارة الكلمات."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    count = len(get_all_words())
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة كلمة",    callback_data="addword")],
        [InlineKeyboardButton("📋 عرض الكلمات",   callback_data="listwords")],
        [InlineKeyboardButton("🔍 بحث عن كلمة",   callback_data="searchword")],
        [InlineKeyboardButton("🗑 حذف كلمة بالاسم", callback_data="delword_by_name")],
        [InlineKeyboardButton("🔙 رجوع",           callback_data="admin_panel")],
    ])
    await q.edit_message_text(
        f"🔄 <b>استبدال الكلمات العالمي</b>\n\n"
        f"📦 الكلمات المحفوظة: <b>{count}</b>\n\n"
        f"كل كلمة مضافة هنا تُستبدل تلقائياً في كل البوت.",
        reply_markup=kb,
        parse_mode="HTML"
    )


async def start_add_word(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """بدء إضافة كلمة: اطلب الكلمة القديمة."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "✏️ <b>إضافة استبدال كلمة</b>\n\n"
        "أرسل الكلمة أو العبارة <b>القديمة</b> التي تريد استبدالها:\n\n"
        "<i>مثال: الخدمات\n(نص عادي فقط — بدون إيموجي مميز)</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 إلغاء", callback_data="admin_words")]
        ]),
        parse_mode="HTML"
    )
    return WW_OLD


async def get_word_old(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال الكلمة القديمة → اطلب الجديدة."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    old = update.message.text.strip()
    if not old:
        await update.message.reply_text("⚠️ أرسل كلمة صالحة.")
        return WW_OLD
    ctx.user_data["ww_old"] = old
    try:
        await update.message.delete()
    except Exception:
        pass
    await update.message.reply_text(
        f"✅ الكلمة القديمة: <code>{old}</code>\n\n"
        f"🆕 أرسل الآن الكلمة أو العبارة <b>الجديدة</b>:\n\n"
        f"<i>✨ يمكنك إرسال إيموجي مميز (Premium Custom Emoji) وسيُحفظ كما هو ويظهر بشكله المميز في البوت.\n\n"
        f"مثال: 🛒 الخدمات الفاخرة</i>",
        parse_mode="HTML"
    )
    return WW_NEW


async def get_word_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال الكلمة الجديدة (تدعم الإيموجي المميز) → حفظ التغيير."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    old = ctx.user_data.pop("ww_old", None)
    # نحفظ text_html لدعم <tg-emoji> (الإيموجي المميز من تيليجرام بريميوم)
    new_html = update.message.text_html or update.message.text or ""
    new_html  = new_html.strip()
    if not old or not new_html:
        return ConversationHandler.END

    add_word(old, new_html)
    try:
        await update.message.delete()
    except Exception:
        pass
    # عرض معاينة مع HTML لإظهار الإيموجي المميز
    await update.message.reply_text(
        f"✅ <b>تم الحفظ!</b>\n\n"
        f"🔴 القديمة: <code>{old}</code>\n"
        f"🟢 الجديدة: {new_html}\n\n"
        f"الآن كل نص يحتوي على «{old}» سيُستبدل تلقائياً.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ إضافة أخرى",  callback_data="addword")],
            [InlineKeyboardButton("📋 عرض الكلمات", callback_data="listwords")],
            [InlineKeyboardButton("🔙 القائمة",      callback_data="admin_words")],
        ])
    )
    return ConversationHandler.END


async def list_words_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض كل الكلمات المخزنة مع معاينة الإيموجي المميز."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    words = get_all_words()
    if not words:
        await q.edit_message_text(
            "📋 لا يوجد كلمات محفوظة بعد.",
            reply_markup=back("admin_words")
        )
        return
    # نبني قائمة نصية مع معاينة HTML (تدعم الإيموجي المميز)
    lines = [f"📋 <b>الكلمات المحفوظة ({len(words)})</b>\n"]
    for w in words:
        old_esc = w["old"].replace("<", "&lt;").replace(">", "&gt;")
        lines.append(f"• <code>{old_esc}</code> → {w['new']}")
    lines.append("\n<i>اضغط على الكلمة أدناه لحذفها:</i>")
    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=_words_kb(words),
        parse_mode="HTML"
    )


async def start_search_word(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """بدء البحث عن كلمة."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "🔍 <b>بحث عن كلمة</b>\n\nأرسل الكلمة للبحث عنها:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 إلغاء", callback_data="admin_words")]
        ]),
        parse_mode="HTML"
    )
    return WW_SEARCH


async def do_search_word(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تنفيذ البحث وعرض النتائج."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    query  = update.message.text.strip()
    results = search_words(query)
    try:
        await update.message.delete()
    except Exception:
        pass
    if not results:
        await update.message.reply_text(
            f"🔍 لا توجد نتائج لـ «<code>{query}</code>»",
            parse_mode="HTML",
            reply_markup=back("admin_words")
        )
    else:
        await update.message.reply_text(
            f"🔍 نتائج «<code>{query}</code>» ({len(results)}):\n"
            f"اضغط للحذف:",
            reply_markup=_words_kb(results),
            parse_mode="HTML"
        )
    return ConversationHandler.END


async def del_word_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """حذف كلمة من القاموس."""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    # البحث عن الكلمة الكاملة (نخزن 30 حرفاً فقط في callback_data)
    partial = q.data[len("delword_"):]
    words   = get_all_words()
    target  = next((w["old"] for w in words if w["old"].startswith(partial) or w["old"] == partial), None)
    if target:
        delete_word(target)
        await q.answer(f"✅ تم حذف: {target[:30]}", show_alert=True)
    else:
        await q.answer("⚠️ لم يتم العثور على الكلمة.", show_alert=True)
    # إعادة عرض القائمة المحدّثة
    words = get_all_words()
    if not words:
        await q.edit_message_text("📋 لا يوجد كلمات محفوظة.", reply_markup=back("admin_words"))
    else:
        await q.edit_message_text(
            f"📋 <b>الكلمات المحفوظة ({len(words)})</b>\nاضغط للحذف:",
            reply_markup=_words_kb(words),
            parse_mode="HTML"
        )


async def start_del_word_by_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """بدء حذف كلمة بإدخال اسمها."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "🗑 <b>حذف كلمة بالاسم</b>\n\n"
        "أرسل الكلمة القديمة (الأصلية) التي تريد حذفها\n"
        "وإعادة البوت لعرضها كما كانت:\n\n"
        "<i>مثال: الخدمات</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 إلغاء", callback_data="admin_words")
        ]])
    )
    return WW_DEL


async def do_del_word_by_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال الاسم → حذف الكلمة."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    name = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass
    words  = get_all_words()
    target = next((w["old"] for w in words if w["old"] == name or w["old"].startswith(name)), None)
    if target:
        delete_word(target)
        await update.message.reply_text(
            f"✅ <b>تم حذف الكلمة</b>\n\n"
            f"🔴 المحذوفة: <code>{target}</code>\n"
            f"الكلمة ستظهر الآن كما كانت في الأصل.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 عرض الكلمات",       callback_data="listwords")],
                [InlineKeyboardButton("🔙 قائمة الكلمات",     callback_data="admin_words")],
            ])
        )
    else:
        await update.message.reply_text(
            f"⚠️ لم يتم العثور على الكلمة: <code>{name}</code>\n\n"
            "تأكد من الاسم وحاول مجدداً.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="admin_words")
            ]])
        )
    return ConversationHandler.END


# ── تجميع كل الـ handlers ────────────────────────

edit_rate_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_rate, pattern="^editrate_")],
    states={EDIT_RATE_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_rate)]},
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

find_user_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_find, pattern="^admin_find$"),
        CallbackQueryHandler(start_ban,  pattern="^admin_(ban|unban)$"),
    ],
    states={FIND_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_find_user)]},
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

add_balance_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_balance, pattern="^admin_add_balance$")],
    states={
        ADM_UID:    [MessageHandler(filters.TEXT & ~filters.COMMAND, get_balance_uid)],
        ADM_ACT:    [CallbackQueryHandler(pick_adm_action, pattern=r"^adm_(add|ded)_\d+$")],
        ADM_AMT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, do_add_balance)],
        ADM_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_deduct_reason)],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

broadcast_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(start_broadcast, pattern="^admin_broadcast$"),
        CommandHandler("broadcast", cmd_broadcast),
    ],
    states={BC_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, do_broadcast)]},
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

add_username_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_username, pattern="^add_username$")],
    states={
        AU_NAME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, au_name)],
        AU_TYPE:  [CallbackQueryHandler(au_type, pattern="^autype_")],
        AU_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, au_price)],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

add_coupon_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_coupon, pattern="^add_coupon$")],
    states={
        CP_CODE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, cp_code)],
        CP_DISC:  [MessageHandler(filters.TEXT & ~filters.COMMAND, cp_disc)],
        CP_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, cp_limit)],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

edit_price_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_price, pattern="^editp_")],
    states={EDIT_PRICE_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_price_val)]},
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

edit_ui_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_ui, pattern="^editui_")],
    states={EDIT_UI_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_ui_text)]},
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

admin_ui_handler = CallbackQueryHandler(admin_ui_menu, pattern="^admin_ui$")

# ── نظام الكلمات ─────────────────────────────────

change_word_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_word, pattern="^addword$")],
    states={
        WW_OLD:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_word_old)],
        WW_NEW:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_word_new)],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

search_word_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_search_word, pattern="^searchword$")],
    states={
        WW_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_search_word)],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
)

del_word_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_del_word_by_name, pattern="^delword_by_name$")],
    states={
        WW_DEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, do_del_word_by_name)],
    },
    fallbacks=[
        CallbackQueryHandler(admin_words_menu, pattern="^admin_words$"),
        MessageHandler(filters.COMMAND, cancel_admin),
    ],
    per_message=False,
)

# ═══════════════════════════════════════════════════════
# 🧑‍💼 إدارة الوكلاء
# ═══════════════════════════════════════════════════════

AG_UID        = 50
AG_RM_UID     = 51
AG_PRICE_SVC  = 52
AG_PRICE_VAL  = 53
AG_CHARGE_UID = 54
AG_CHARGE_AMT = 55

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "─────────────────────"


async def admin_agents_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    agents = get_agents()
    agent_prices = get_all_agent_prices()

    if agents:
        lines = "\n".join(
            f"👤 <code>{a['user_id']}</code>  @{a['username'] or '—'}"
            f"  |  💰 <b>{a['balance']:.2f}$</b>  🔒 USD"
            for a in agents
        )
        header = f"<b>إجمالي الوكلاء: {len(agents)}</b>"
    else:
        lines = "لا يوجد وكلاء مسجّلون بعد."
        header = "<b>لا يوجد وكلاء</b>"

    price_lines = ""
    if agent_prices:
        price_lines = "\n\n<b>💲 أسعار الوكلاء المخصصة:</b>\n" + "\n".join(
            f"  • {p['service']}: <b>{p['price']}$</b>"
            for p in agent_prices
        )
    else:
        price_lines = "\n\n<i>💡 لا توجد أسعار مخصصة — الوكلاء يستخدمون الأسعار العادية</i>"

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ إضافة وكيل",  callback_data="ag_add"),
            InlineKeyboardButton("➖ إزالة وكيل",  callback_data="ag_remove"),
        ],
        [
            InlineKeyboardButton("💰 شحن رصيد وكيل", callback_data="ag_charge"),
        ],
        [
            InlineKeyboardButton("💲 أسعار الوكلاء", callback_data="ag_prices"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
    ])
    await q.edit_message_text(
        f"<b>{SEP}\n🧑‍💼 إدارة الوكلاء\n{SEP}</b>\n\n"
        f"{header}\n{SEP2}\n{lines}{price_lines}",
        reply_markup=kb,
        parse_mode="HTML",
    )


async def ag_add_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.edit_message_text(
        f"<b>{SEP}\n➕ إضافة وكيل\n{SEP}</b>\n\n"
        "أرسل <b>ID المستخدم</b> الذي تريد تعيينه وكيلاً:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_agents")]]),
        parse_mode="HTML",
    )
    return AG_UID


async def ag_add_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقم ID صحيح.")
        return AG_UID
    set_agent_status(uid, 1)
    u = get_user(uid)
    name = f"@{u['username']}" if u and u['username'] else f"<code>{uid}</code>"
    await update.message.reply_text(
        f"✅ تم تعيين {name} كوكيل بنجاح.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الوكلاء", callback_data="admin_agents")]]),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def ag_remove_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.edit_message_text(
        f"<b>{SEP}\n➖ إزالة وكيل\n{SEP}</b>\n\n"
        "أرسل <b>ID المستخدم</b> الذي تريد إزالته من الوكلاء:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_agents")]]),
        parse_mode="HTML",
    )
    return AG_RM_UID


async def ag_remove_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقم ID صحيح.")
        return AG_RM_UID
    set_agent_status(uid, 0)
    await update.message.reply_text(
        f"✅ تم إزالة <code>{uid}</code> من قائمة الوكلاء.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الوكلاء", callback_data="admin_agents")]]),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def ag_prices_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    from db import get_all_prices

    # get_all_prices() يُعيد dict {service_name: price}
    agent_prices_map = {p["service"]: p["price"] for p in get_all_agent_prices()}
    all_services     = get_all_prices()   # dict {name: price}

    lines = []
    rows  = []
    for name, normal_p in all_services.items():
        agent_p = agent_prices_map.get(name)
        if agent_p is not None:
            lines.append(f"✅ <code>{name}</code>: <b>{agent_p}$</b>  <i>(عادي: {normal_p}$)</i>")
            rows.append([
                InlineKeyboardButton(f"✏️ {name}: {agent_p}$", callback_data=f"ag_pricesvc_{name}"),
                InlineKeyboardButton("🗑", callback_data=f"ag_delprice_{name}"),
            ])
        else:
            lines.append(f"⬜ <code>{name}</code>: عادي <b>{normal_p}$</b>")
            rows.append([
                InlineKeyboardButton(f"✏️ تعيين وكيل: {name}", callback_data=f"ag_pricesvc_{name}"),
            ])

    price_text = "\n".join(lines) if lines else "لا توجد خدمات مضافة بعد — أضف أسعاراً أولاً."
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_agents")])

    legend = "✅ = سعر وكيل مخصص  |  ⬜ = يستخدم السعر العادي"
    await q.edit_message_text(
        f"<b>{SEP}\n💲 أسعار الوكلاء — كل الخدمات\n{SEP}</b>\n"
        f"<i>{legend}</i>\n\n{price_text}",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML",
    )


async def ag_setprice_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    from db import get_all_prices
    prices = get_all_prices()
    kb_rows = [[InlineKeyboardButton(p["service"], callback_data=f"ag_pricesvc_{p['service']}")]
               for p in prices]
    kb_rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="ag_prices")])
    await q.edit_message_text(
        f"<b>{SEP}\n✏️ تعيين سعر وكيل\n{SEP}</b>\n\nاختر الخدمة:",
        reply_markup=InlineKeyboardMarkup(kb_rows),
        parse_mode="HTML",
    )
    return AG_PRICE_SVC


async def ag_pricesvc_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    svc = q.data.split("ag_pricesvc_", 1)[1]
    ctx.user_data["ag_price_svc"] = svc
    curr = get_agent_price(svc)
    curr_txt = f"{curr}$" if curr is not None else "غير محدد"
    await q.edit_message_text(
        f"<b>{SEP}\n✏️ سعر وكيل: <code>{svc}</code>\n{SEP}</b>\n\n"
        f"السعر الحالي للوكيل: <b>{curr_txt}</b>\n\n"
        "أرسل السعر الجديد بالدولار:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="ag_prices")]]),
        parse_mode="HTML",
    )
    return AG_PRICE_VAL


async def ag_priceval_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        val = float(update.message.text.strip())
        if val < 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقماً صحيحاً موجباً.")
        return AG_PRICE_VAL
    svc = ctx.user_data.get("ag_price_svc", "")
    set_agent_price(svc, val)
    await update.message.reply_text(
        f"✅ تم تعيين سعر الوكيل لـ <code>{svc}</code>: <b>{val}$</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 أسعار الوكلاء", callback_data="ag_prices")]]),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def ag_delprice_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    svc = q.data.split("ag_delprice_", 1)[1]
    delete_agent_price(svc)
    await q.answer(f"✅ تم حذف سعر الوكيل لـ {svc}", show_alert=True)
    await ag_prices_cb(update, ctx)


async def ag_charge_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    await q.edit_message_text(
        f"<b>{SEP}\n💰 شحن رصيد وكيل\n{SEP}</b>\n\n"
        "أرسل <b>ID الوكيل</b> الذي تريد شحن رصيده:",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_agents")]]),
        parse_mode="HTML",
    )
    return AG_CHARGE_UID


async def ag_charge_uid_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        uid = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقم ID صحيح.")
        return AG_CHARGE_UID
    u = get_user(uid)
    if not u or not u.get("is_agent"):
        await update.message.reply_text(
            f"⚠️ المستخدم <code>{uid}</code> ليس وكيلاً.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الوكلاء", callback_data="admin_agents")]]),
            parse_mode="HTML",
        )
        return ConversationHandler.END
    ctx.user_data["ag_charge_uid"] = uid
    name = f"@{u['username']}" if u.get("username") else f"<code>{uid}</code>"
    await update.message.reply_text(
        f"👤 الوكيل: {name}\n"
        f"💰 الرصيد الحالي: <b>{u['balance']:.2f}$</b>\n\n"
        "أرسل المبلغ بالدولار (مثال: 10 أو -5 للخصم):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="admin_agents")]]),
        parse_mode="HTML",
    )
    return AG_CHARGE_AMT


async def ag_charge_amt_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        amount = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقماً صحيحاً (مثال: 10 أو -5).")
        return AG_CHARGE_AMT
    uid = ctx.user_data.get("ag_charge_uid")
    if not uid:
        await update.message.reply_text("⚠️ انتهت الجلسة، ابدأ من جديد.")
        return ConversationHandler.END
    from db import add_balance, get_user
    add_balance(uid, amount, "شحن رصيد وكيل من الأدمن", "إيداع")
    u = get_user(uid)
    new_bal = u["balance"] if u else 0
    name = f"@{u['username']}" if u and u.get("username") else f"<code>{uid}</code>"
    sign = "+" if amount >= 0 else ""
    await update.message.reply_text(
        f"✅ تم شحن رصيد الوكيل {name}\n"
        f"📊 التغيير: <b>{sign}{amount:.2f}$</b>\n"
        f"💰 الرصيد الجديد: <b>{new_bal:.2f}$</b>",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الوكلاء", callback_data="admin_agents")]]),
        parse_mode="HTML",
    )
    return ConversationHandler.END


async def cancel_agent(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("❌ تم إلغاء العملية.")
    return ConversationHandler.END


add_agent_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(ag_add_start, pattern="^ag_add$")],
    states={
        AG_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_add_recv)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_agent),
        CallbackQueryHandler(cancel_agent, pattern="^admin_agents$"),
    ],
    per_message=False,
)

remove_agent_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(ag_remove_start, pattern="^ag_remove$")],
    states={
        AG_RM_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_remove_recv)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_agent),
        CallbackQueryHandler(cancel_agent, pattern="^admin_agents$"),
    ],
    per_message=False,
)

agent_price_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(ag_setprice_start,  pattern="^ag_setprice$"),
        CallbackQueryHandler(ag_pricesvc_pick,   pattern="^ag_pricesvc_"),  # دخول مباشر من قائمة الأسعار
    ],
    states={
        AG_PRICE_SVC: [CallbackQueryHandler(ag_pricesvc_pick, pattern="^ag_pricesvc_")],
        AG_PRICE_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_priceval_recv)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_agent),
        CallbackQueryHandler(cancel_agent, pattern="^ag_prices$"),
    ],
    per_message=False,
)

agent_charge_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(ag_charge_start, pattern="^ag_charge$")],
    states={
        AG_CHARGE_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_charge_uid_recv)],
        AG_CHARGE_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ag_charge_amt_recv)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_agent),
        CallbackQueryHandler(cancel_agent, pattern="^admin_agents$"),
    ],
    per_message=False,
)

admin_agents_handler = CallbackQueryHandler(admin_agents_cb,  pattern="^admin_agents$")
ag_prices_handler    = CallbackQueryHandler(ag_prices_cb,     pattern="^ag_prices$")
ag_delprice_handler  = CallbackQueryHandler(ag_delprice_cb,   pattern="^ag_delprice_")


# ── وضع الصيانة ──────────────────────────────────

async def toggle_maintenance_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    current = "on" if is_maintenance() else "off"
    new_val = "off" if current == "on" else "on"
    set_str_setting("maintenance", new_val)
    status  = "🟢 مفعّل" if new_val == "on" else "🔴 معطّل"
    await q.answer(f"وضع الصيانة {status}", show_alert=True)
    # أعد رسم لوحة التحكم
    await q.edit_message_text("👑 <b>لوحة تحكم المالك</b>", reply_markup=admin_panel(), parse_mode="HTML")


admin_maintenance_handler = CallbackQueryHandler(toggle_maintenance_cb, pattern="^admin_maintenance$")

admin_words_handler  = CallbackQueryHandler(admin_words_menu, pattern="^admin_words$")


# ══════════════════════════════════════════════════════
# نظام الإحالات — تعديل نسبة العمولة
# ══════════════════════════════════════════════════════

REF_PERCENT_VAL = 60


async def admin_ref_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    percent = get_ref_percent()
    await q.message.reply_text(
        f"💸 <b>نسبة العمولة الحالية: {percent:.1f}%</b>\n\n"
        f"أرسل النسبة الجديدة (مثال: 15 أو 7.5):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")
        ]])
    )
    return REF_PERCENT_VAL


async def save_ref_percent_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    try:
        val = float(update.message.text.strip().replace(",", "."))
        if val < 0 or val > 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أرسل رقماً بين 0 و 100 (مثال: 10 أو 7.5).")
        return REF_PERCENT_VAL
    set_ref_percent(val)
    await update.message.reply_text(
        f"✅ تم تحديث نسبة العمولة إلى <b>{val:.1f}%</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 لوحة التحكم", callback_data="admin_panel")
        ]])
    )
    return ConversationHandler.END


edit_ref_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(admin_ref_cb, pattern="^admin_ref$")],
    states={
        REF_PERCENT_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_ref_percent_cb)],
    },
    fallbacks=[
        MessageHandler(filters.COMMAND, cancel_admin),
        CallbackQueryHandler(cancel_admin, pattern="^admin_panel$"),
    ],
    per_message=False,
    allow_reentry=True,
)

admin_ref_handler = CallbackQueryHandler(admin_ref_cb, pattern="^admin_ref$")
list_words_handler   = CallbackQueryHandler(list_words_cb,    pattern="^listwords$")
del_word_handler     = CallbackQueryHandler(del_word_cb,      pattern="^delword_")

admin_handler        = CommandHandler("admin",       cmd_admin)
stats_handler        = CommandHandler("stats",       cmd_stats)
addbal_cmd_handler   = CommandHandler("add_balance", cmd_add_balance)
prices_cmd_handler   = CommandHandler("prices",      admin_prices_cmd)
admin_panel_handler  = CallbackQueryHandler(admin_panel_cb,     pattern="^admin_panel$")
admin_users_handler  = CallbackQueryHandler(admin_users_cb,     pattern="^admin_users$")
admin_stats_handler  = CallbackQueryHandler(admin_stats_cb,     pattern="^admin_stats$")
admin_orders_handler = CallbackQueryHandler(admin_orders_cb,    pattern="^admin_orders$")
admin_curr_handler   = CallbackQueryHandler(admin_currency_cb,  pattern="^admin_currency$")
admin_unames_handler = CallbackQueryHandler(admin_usernames_cb, pattern="^admin_usernames$")
admin_cpns_handler   = CallbackQueryHandler(admin_coupons_cb,   pattern="^admin_coupons$")
admin_prices_handler = CallbackQueryHandler(show_prices_cb,     pattern="^admin_prices$")
list_unames_handler  = CallbackQueryHandler(list_usernames_cb,  pattern="^list_usernames$")
del_uname_handler    = CallbackQueryHandler(del_username_cb,    pattern="^deluname_")
list_cpns_handler    = CallbackQueryHandler(list_coupons_cb,    pattern="^list_coupons$")
del_cpn_handler      = CallbackQueryHandler(del_coupon_cb,      pattern="^delcoupon_")
done_handler         = CallbackQueryHandler(done_order,         pattern="^done_")
process_ord_handler  = CallbackQueryHandler(process_order,      pattern="^process_")
cancel_ord_handler   = CallbackQueryHandler(cancel_order,       pattern="^cancel_")


# ════════════════════════════════════════════════════
# ── إدارة البطاقات (سوا / لايك كارد) ────────────
# ════════════════════════════════════════════════════

CARD_RATE_STATE = 60  # حالة ConversationHandler


async def admin_cards_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """قائمة إدارة البطاقات"""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()

    rate_sawa = get_card_rate("sawa")
    rate_like = get_card_rate("like")

    await q.edit_message_text(
        f"💳 <b>إدارة البطاقات</b>\n\n"
        f"📶 سعر سوا:       <b>{rate_sawa:.2f}</b> (كل 100 ريال)\n"
        f"💳 سعر لايك كارد: <b>{rate_like:.2f}</b> (كل 100 ريال)\n\n"
        f"اضغط لتعديل المعدل:",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✏️ سعر سوا",       callback_data="admin_rate_sawa"),
                InlineKeyboardButton("✏️ سعر لايك كارد", callback_data="admin_rate_like"),
            ],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
        ]),
        parse_mode="HTML",
    )


async def admin_rate_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """بدء تعديل معدل البطاقة"""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()

    card_type = q.data.split("_")[2]  # admin_rate_sawa → sawa
    ctx.user_data["edit_card_rate"] = card_type
    label = "سوا" if card_type == "sawa" else "لايك كارد"
    current = get_card_rate(card_type)

    await q.edit_message_text(
        f"✏️ أدخل المعدل الجديد لـ <b>{label}</b>\n"
        f"الحالي: <b>{current:.2f}</b> دولار لكل 100 ريال\n\n"
        f"<i>مثال: 27 يعني كل 100 ريال = 27 سنت</i>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data="admin_cards"),
        ]]),
        parse_mode="HTML",
    )
    return CARD_RATE_STATE


async def admin_rate_save(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """حفظ المعدل الجديد"""
    if not is_admin(update.effective_user.id):
        return
    card_type = ctx.user_data.pop("edit_card_rate", None)
    if not card_type:
        return ConversationHandler.END
    try:
        val = float(update.message.text.strip())
        if val <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ رقم غير صحيح. أعد الإدخال:")
        ctx.user_data["edit_card_rate"] = card_type
        return CARD_RATE_STATE

    set_card_rate(card_type, val)
    label = "سوا" if card_type == "sawa" else "لايك كارد"
    await update.message.reply_text(
        f"✅ تم تحديث معدل <b>{label}</b> إلى <b>{val:.2f}</b> دولار/100 ريال",
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ── نظام الحماية: عرض نقاط الخطورة ──────────────

async def admin_risk_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عرض نقاط الخطورة لأعلى المستخدمين"""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()

    scores = get_all_risk_scores()
    if not scores:
        text = "✅ لا يوجد مستخدمون خطرون حالياً."
    else:
        lines = ["⚠️ <b>نقاط الخطورة</b>\n"]
        for uid, score in scores:
            lines.append(f"• <code>{uid}</code> — {score} نقطة")
        text = "\n".join(lines)

    await q.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
        ]),
        parse_mode="HTML",
    )


async def admin_reset_risk_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إعادة ضبط نقاط خطورة مستخدم"""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    await q.answer()
    uid = int(q.data.split("_")[3])
    reset_risk(uid)
    await q.answer(f"✅ تم إعادة ضبط نقاط {uid}", show_alert=True)


# ── ConversationHandler لتعديل معدل البطاقات ──

edit_card_rate_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(admin_rate_start, pattern="^admin_rate_(sawa|like)$")],
    states={
        CARD_RATE_STATE: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, admin_rate_save),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_admin, pattern="^admin_panel$"),
        MessageHandler(filters.COMMAND, cancel_admin),
    ],
    per_message=False,
    allow_reentry=True,
)

admin_cards_handler    = CallbackQueryHandler(admin_cards_cb,      pattern="^admin_cards$")
admin_risk_handler     = CallbackQueryHandler(admin_risk_cb,       pattern="^admin_risk$")
admin_reset_risk_hndlr = CallbackQueryHandler(admin_reset_risk_cb, pattern="^admin_resetrisk_")


# ════════════════════════════════════════════════
# ── موافقة السحب من الأدمن ───────────────────────
# ════════════════════════════════════════════════

WITHDRAW_APPROVE_AMT = 30

async def wd_approve_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن يضغط 'قبول السحب' → يُطلب المبلغ المخصوم"""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return await q.answer("❌ غير مصرح", show_alert=True)
    await q.answer()
    wid = int(q.data.split("_")[-1])
    ctx.user_data["wd_approve_id"] = wid
    wdr = get_withdrawal(wid)
    if not wdr or wdr["status"] != "pending":
        await q.edit_message_text("⚠️ الطلب غير موجود أو تمت معالجته.")
        return ConversationHandler.END
    uid      = wdr["user_id"]
    card_bal = get_total_card_balance(uid)
    await q.message.reply_text(
        f"💸 <b>طلب سحب #{wid}</b>\n"
        f"👤 المستخدم: <code>{uid}</code>\n"
        f"🌍 الدولة: {wdr['country']}\n"
        f"💳 المحفظة: {wdr['method']}\n"
        f"📝 المعلومات: <code>{wdr['info']}</code>\n"
        f"💳 رصيد بطاقاته: <b>{card_bal:.4f}$</b>\n\n"
        f"أدخل مبلغ الخصم بالدولار:",
        parse_mode="HTML",
    )
    return WITHDRAW_APPROVE_AMT


async def wd_approve_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن يُدخل المبلغ → خصم الرصيد + إشعار المستخدم"""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    wid = ctx.user_data.pop("wd_approve_id", None)
    if not wid:
        return ConversationHandler.END
    try:
        amount = float(update.message.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ أدخل رقمًا صحيحًا.")
        return WITHDRAW_APPROVE_AMT

    wdr = get_withdrawal(wid)
    if not wdr or wdr["status"] != "pending":
        await update.message.reply_text("⚠️ الطلب غير موجود أو تمت معالجته.")
        return ConversationHandler.END

    uid      = wdr["user_id"]
    card_bal = get_total_card_balance(uid)
    if card_bal < amount:
        await update.message.reply_text(
            f"❌ رصيد بطاقات المستخدم غير كافٍ.\n"
            f"💳 رصيد بطاقاته: <b>{card_bal:.4f}$</b>",
            parse_mode="HTML",
        )
        return WITHDRAW_APPROVE_AMT

    deduct_card_balance(uid, amount)
    update_withdrawal(wid, "approved", amount)
    await update.message.reply_text(
        f"✅ تم قبول السحب #{wid}\n"
        f"💸 تم خصم <b>{amount}$</b> من رصيد بطاقات <code>{uid}</code>",
        parse_mode="HTML",
    )
    try:
        user_c = get_user(uid)
        from config import CURRENCY_SYMBOLS
        from db import convert_from_usd, get_total_card_balance
        cur    = user_c["currency"] if user_c else "USD"
        sym    = CURRENCY_SYMBOLS.get(cur, cur)
        amount_loc = convert_from_usd(amount, cur)
        remaining  = convert_from_usd(get_total_card_balance(uid), cur)
        await ctx.bot.send_message(
            uid,
            f"✅ <b>تمت الموافقة على طلب سحبك!</b>\n\n"
            f"💸 تم صرف <b>{amount_loc:.2f} {sym}</b>\n"
            f"🌍 الدولة: {wdr['country']}\n"
            f"💳 طريقة الاستلام: {wdr['method']}\n"
            f"💳 رصيد بطاقاتك المتبقي: <b>{remaining:.2f} {sym}</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass
    return ConversationHandler.END


async def wd_reject_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن يضغط رفض — يطلب سبب الرفض."""
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return await q.answer("❌ غير مصرح", show_alert=True)
    await q.answer()
    wid = int(q.data.split("_")[-1])
    wdr = get_withdrawal(wid)
    if not wdr or wdr["status"] != "pending":
        await q.edit_message_text("⚠️ الطلب غير موجود أو تمت معالجته.")
        return ConversationHandler.END
    ctx.user_data["wd_reject_id"]  = wid
    ctx.user_data["wd_reject_uid"] = wdr["user_id"]
    await q.message.reply_text(
        f"❌ رفض طلب السحب #{wid}\n📝 اكتب سبب الرفض (سيُرسل للعميل):"
    )
    return WD_REJECT_REASON


async def wd_reject_reason(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال سبب الرفض — معالج ذو أولوية عالية (group=-2)."""
    if not is_admin(update.effective_user.id):
        return
    wid = ctx.user_data.get("wd_reject_id")
    if not wid:
        return                              # ليس في وضع الرفض
    reason = update.message.text.strip()
    uid    = ctx.user_data.pop("wd_reject_uid", None)
    ctx.user_data.pop("wd_reject_id", None)
    update_withdrawal(wid, "rejected", 0)
    await update.message.reply_text(f"❌ تم رفض طلب السحب #{wid}")
    if uid:
        try:
            await ctx.bot.send_message(
                uid,
                f"❌ <b>تم رفض طلب سحبك #{wid}</b>\n"
                f"📝 السبب: {reason}",
                parse_mode="HTML",
            )
        except Exception:
            pass
    raise ApplicationHandlerStop        # منع المعالجات الأخرى من التقاط هذه الرسالة


wd_approve_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(wd_approve_start, pattern=r"^wd_approve_\d+$")],
    states={
        WITHDRAW_APPROVE_AMT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, wd_approve_amount),
        ],
    },
    fallbacks=[MessageHandler(filters.COMMAND, cancel_admin)],
    per_message=False,
    allow_reentry=True,
)

wd_reject_handler         = CallbackQueryHandler(wd_reject_start,  pattern=r"^wd_reject_\d+$")
wd_reject_pending_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, wd_reject_reason)
review_dismiss_handler    = CallbackQueryHandler(review_dismiss_cb, pattern="^review_dismiss$")


# ════════════════════════════════════════════════
# أمر /setgroup — تسجيل مجموعة الطلبات
# ════════════════════════════════════════════════

async def setgroup_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    استخدم هذا الأمر من داخل المجموعة التي تريدها لاستقبال إشعارات الطلبات.
    يجب أن يكون مُرسِله هو الأدمن.
    """
    user = update.effective_user
    chat = update.effective_chat

    if user.id != ADMIN_ID:
        return

    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text(
            "⚠️ يجب إرسال هذا الأمر من داخل المجموعة التي تريد تفعيلها."
        )
        return

    set_order_group(chat.id)
    gid = get_order_group()
    await update.message.reply_text(
        f"✅ <b>تم تفعيل هذه المجموعة لاستقبال إشعارات الطلبات</b>\n"
        f"🆔 معرف المجموعة: <code>{gid}</code>\n\n"
        f"سيتم إرسال جميع الطلبات الجديدة هنا.",
        parse_mode="HTML",
    )


async def unsetgroup_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إلغاء تفعيل مجموعة الطلبات."""
    if update.effective_user.id != ADMIN_ID:
        return
    set_order_group(0)
    await update.message.reply_text("✅ تم إلغاء تفعيل مجموعة الطلبات.")


setgroup_handler   = CommandHandler("setgroup",   setgroup_command)
unsetgroup_handler = CommandHandler("unsetgroup", unsetgroup_command)


# ════════════════════════════════════════════════
# كشف حساب عميل — Customer Account Statement
# ════════════════════════════════════════════════

_STMT_SEP  = "━━━━━━━━━━━━━━━━━━━━"
_STMT_SEP2 = "— — — — — — — — — —"

# ── مفتاح الحالة في user_data ──
_STMT_KEY = "__stmt_mode__"


async def adm_stmt_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """زر 'كشف حساب عميل' — يطلب UID ويضع البوت في وضع انتظار الـ ID."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    ctx.user_data[_STMT_KEY] = True
    await q.message.reply_text(
        "📊 <b>كشف حساب عميل</b>\n\n"
        "أرسل <b>معرف المستخدم (User ID)</b> للاستعلام عنه:\n"
        "<i>مثال: 123456789</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel")
        ]]),
    )


_ORDERS_PER_PAGE = 15    # عدد الطلبات في كل صفحة
_MAX_PAGE_LEN    = 3800  # الحد الأقصى لعدد حروف الصفحة (أقل من حد تيليجرام 4096)


def _safe_split_pages(pages: list[str]) -> list[str]:
    """يضمن أن كل صفحة لا تتجاوز _MAX_PAGE_LEN حرفاً بالتقسيم على الأسطر."""
    result: list[str] = []
    for page in pages:
        if len(page) <= _MAX_PAGE_LEN:
            result.append(page)
            continue
        lines = page.split("\n")
        current: list[str] = []
        size = 0
        for line in lines:
            ln = len(line) + 1
            if size + ln > _MAX_PAGE_LEN and current:
                result.append("\n".join(current))
                current, size = [], 0
            current.append(line)
            size += ln
        if current:
            result.append("\n".join(current))
    return result if result else [""]


_TX_PER_PAGE_ADM = 15


def _build_stmt_pages(target_uid: int, u: dict, txs: list) -> list[str]:
    """
    يبني صفحات HTML لكشف الحساب من جدول transactions.
    amount > 0 → له (إيداع)   |   amount < 0 → عليه (خصم/شراء)
    """
    username_txt = f"@{u.get('username')}" if u.get("username") else "—"
    first_name   = (u.get("first_name") or u.get("username") or "—").strip() or "—"

    total_in  = sum(t.get("amount", 0) for t in txs if (t.get("amount") or 0) > 0)
    total_out = sum(abs(t.get("amount", 0)) for t in txs if (t.get("amount") or 0) < 0)

    header = "\n".join([
        _STMT_SEP,
        "📊 <b>كشف حساب العميل</b>",
        _STMT_SEP,
        f"👤 <b>الاسم:</b> {first_name}",
        f"🆔 <b>UID:</b> <code>{target_uid}</code>",
        f"📛 <b>يوزر:</b> {username_txt}",
        f"💰 <b>الرصيد:</b> {u.get('balance', 0) or 0:.4f} USD",
        f"🏆 <b>VIP:</b> {u.get('vip_level') or 'normal'}",
        f"🚫 <b>محظور:</b> {'نعم ⛔' if u.get('is_banned') else 'لا ✅'}",
        f"📥 <b>إجمالي الإيداعات:</b> +{total_in:.4f}$",
        f"📤 <b>إجمالي الخصومات:</b> -{total_out:.4f}$",
        f"📋 <b>عدد الحركات:</b> {len(txs)}",
        _STMT_SEP2,
    ])

    chunks: list[list] = [txs[i:i + _TX_PER_PAGE_ADM]
                          for i in range(0, max(len(txs), 1), _TX_PER_PAGE_ADM)]
    if not txs:
        chunks = [[]]

    pages: list[str] = []
    for ci, chunk in enumerate(chunks):
        parts = [header if ci == 0 else _STMT_SEP]
        start = ci * _TX_PER_PAGE_ADM + 1
        end   = start + len(chunk) - 1

        if txs:
            parts.append(f"\n📋 <b>الحركات ({start}–{end} من {len(txs)}):</b>")
            for t in chunk:
                amt       = t.get("amount") or 0
                note      = str(t.get("note") or t.get("type") or "—")[:35]
                date      = str(t.get("created_at") or "")[:10]
                bal_after = t.get("balance_after") or 0

                if amt > 0:
                    icon       = "🟢"
                    amount_str = f"<b>+{amt:.4f}$</b>"
                    col        = "له"
                else:
                    icon       = "🔴"
                    amount_str = f"<b>-{abs(amt):.4f}$</b>"
                    col        = "عليه"

                parts.append(
                    f"  {icon} {col}: {amount_str}\n"
                    f"     📝 {note}\n"
                    f"     📅 {date}  |  💰 رصيد: {bal_after:.4f}$"
                )
        else:
            parts.append("\n  لا توجد حركات مسجّلة لهذا العميل بعد")

        pages.append("\n".join(parts))

    return _safe_split_pages(pages)


async def adm_stmt_msg(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    معالج ذو أولوية عالية (group=-1).
    يُنشَّط فقط عندما يكون الأدمن في وضع كشف الحساب.
    """
    if not ctx.user_data.get(_STMT_KEY):
        return          # ليس في وضع الكشف — دع المعالجات الأخرى تعمل

    ctx.user_data.pop(_STMT_KEY, None)   # أوقف الوضع بعد محاولة واحدة

    uid_text = update.message.text.strip()
    if not uid_text.lstrip("-").isdigit():
        await update.message.reply_text(
            "❌ معرف غير صحيح. أرسل رقماً مثل: <code>123456789</code>",
            parse_mode="HTML",
        )
        raise ApplicationHandlerStop

    target_uid = int(uid_text)
    _u = get_user(target_uid)

    if not _u:
        await update.message.reply_text(
            f"❌ لا يوجد مستخدم بالمعرف <code>{target_uid}</code>.",
            parse_mode="HTML",
            reply_markup=back("admin_panel"),
        )
        raise ApplicationHandlerStop

    u   = dict(_u)
    txs = [dict(t) for t in get_transactions(target_uid, limit=200)]

    pages = _build_stmt_pages(target_uid, u, txs)

    # حفظ الصفحات في user_data
    ctx.user_data[f"stmt_{target_uid}"] = pages

    def _stmt_kb(page: int, total: int, uid: int) -> InlineKeyboardMarkup:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"stmt_page_{uid}_{page-1}"))
        if page < total - 1:
            nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"stmt_page_{uid}_{page+1}"))
        rows = []
        if nav:
            rows.append(nav)
        rows.append([
            InlineKeyboardButton("📊 بحث عن عميل آخر", callback_data="admin_cust_stmt"),
            InlineKeyboardButton("🔙 لوحة الأدمن",     callback_data="admin_panel"),
        ])
        return InlineKeyboardMarkup(rows)

    await update.message.reply_text(
        pages[0],
        parse_mode="HTML",
        reply_markup=_stmt_kb(0, len(pages), target_uid),
    )

    # ── إرسال PDF للأدمن ──────────────────────────────────────
    try:
        import io as _io
        from pdf_gen import generate_statement_pdf
        pdf = generate_statement_pdf(target_uid)
        if pdf:
            await update.message.reply_document(
                document=_io.BytesIO(pdf),
                filename=f"statement_{target_uid}.pdf",
                caption=f"📊 كشف حساب العميل <code>{target_uid}</code> بصيغة PDF",
                parse_mode="HTML",
            )
    except Exception as _pe:
        log.warning(f"فشل إنشاء PDF للأدمن: {_pe}")

    raise ApplicationHandlerStop   # لا تُمرّر الرسالة لأي معالج آخر


async def stmt_page_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """معالج تنقل صفحات كشف الحساب."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    # pattern: stmt_page_{uid}_{page}
    parts     = q.data.split("_")   # ['stmt', 'page', uid, page]
    target_uid = int(parts[2])
    page       = int(parts[3])
    pages      = ctx.user_data.get(f"stmt_{target_uid}", [])
    if not pages or page >= len(pages):
        await q.answer("⚠️ انتهت الجلسة، ابحث من جديد.", show_alert=True)
        return

    def _stmt_kb(p: int, total: int, uid: int) -> InlineKeyboardMarkup:
        nav = []
        if p > 0:
            nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"stmt_page_{uid}_{p-1}"))
        if p < total - 1:
            nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"stmt_page_{uid}_{p+1}"))
        rows = []
        if nav:
            rows.append(nav)
        rows.append([
            InlineKeyboardButton("📊 بحث عن عميل آخر", callback_data="admin_cust_stmt"),
            InlineKeyboardButton("🔙 لوحة الأدمن",     callback_data="admin_panel"),
        ])
        return InlineKeyboardMarkup(rows)

    await q.edit_message_text(
        pages[page],
        parse_mode="HTML",
        reply_markup=_stmt_kb(page, len(pages), target_uid),
    )


# معالج الـ CallbackQuery لزر "📊 كشف حساب عميل"
cust_stmt_cb_handler = CallbackQueryHandler(adm_stmt_start, pattern="^admin_cust_stmt$")

# معالج تنقل صفحات كشف الحساب
stmt_page_handler = CallbackQueryHandler(stmt_page_cb, pattern="^stmt_page_")

# معالج الرسائل النصية — أولوية عالية group=-1
cust_stmt_msg_handler = MessageHandler(
    filters.TEXT & ~filters.COMMAND,
    adm_stmt_msg,
)


# ════════════════════════════════════════════════
# إعداد الحساب المساعد (Telethon / @stc25bot)
# ════════════════════════════════════════════════

WAIT_ASST_API     = 600
WAIT_ASST_SESSION = 601


def _asst_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔑 إعداد API",          callback_data="asst_set_api"),
            InlineKeyboardButton("📋 String Session",      callback_data="asst_set_session"),
        ],
        [InlineKeyboardButton("🔙 لوحة التحكم",           callback_data="admin_panel")],
    ])


async def admin_assistant_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    from assistant import get_status_text
    from db import get_setting
    api_id   = get_setting("asst_api_id")   or "—"
    api_hash = get_setting("asst_api_hash") or "—"
    has_sess = "✅ محفوظ" if get_setting("asst_session") else "❌ غير مُعدّ"
    status   = get_status_text()
    await q.edit_message_text(
        f"🤖 <b>إعداد الحساب المساعد</b>\n\n"
        f"الحالة: {status}\n\n"
        f"🆔 API ID: <code>{api_id}</code>\n"
        f"🔐 API Hash: <code>{api_hash}</code>\n"
        f"📋 String Session: {has_sess}\n\n"
        f"<i>الحساب المساعد يرسل أكواد السوا إلى @stc25bot ويقرأ الرد تلقائياً.</i>",
        parse_mode="HTML",
        reply_markup=_asst_kb(),
    )


async def asst_set_api_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    ctx.user_data["asst_edit_msg"] = q.message.message_id
    await q.edit_message_text(
        "🔑 <b>إعداد API</b>\n\n"
        "أرسل بيانات API بالصيغة التالية:\n"
        "<code>API_ID,API_HASH</code>\n\n"
        "<i>مثال: 12345678,abcdef1234567890abcdef</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 إلغاء", callback_data="admin_assistant"),
        ]]),
    )
    return WAIT_ASST_API


async def asst_save_api(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    text = update.message.text.strip()
    if "," not in text:
        await update.message.reply_text(
            "❌ الصيغة خاطئة. أرسل: <code>API_ID,API_HASH</code>",
            parse_mode="HTML",
        )
        return WAIT_ASST_API
    parts = text.split(",", 1)
    api_id   = parts[0].strip()
    api_hash = parts[1].strip()
    if not api_id.isdigit():
        await update.message.reply_text("❌ API ID يجب أن يكون أرقاماً فقط.")
        return WAIT_ASST_API
    from db import set_setting
    set_setting("asst_api_id",   api_id)
    set_setting("asst_api_hash", api_hash)
    await update.message.reply_text(
        "✅ تم حفظ بيانات API بنجاح!\n\n"
        "أعد تشغيل البوت بعد إضافة String Session.",
    )
    return ConversationHandler.END


async def asst_set_session_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await q.edit_message_text(
        "📋 <b>إضافة String Session</b>\n\n"
        "أرسل الـ String Session للحساب المساعد الآن.\n\n"
        "<i>يمكن الحصول عليه عبر Telethon SessionGenerator.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 إلغاء", callback_data="admin_assistant"),
        ]]),
    )
    return WAIT_ASST_SESSION


async def asst_save_session(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    session = update.message.text.strip()
    if len(session) < 20:
        await update.message.reply_text("❌ String Session يبدو غير صالح، أعد المحاولة.")
        return WAIT_ASST_SESSION
    from db import set_setting
    set_setting("asst_session", session)
    await update.message.reply_text(
        "✅ تم حفظ String Session بنجاح!\n\n"
        "أعد تشغيل البوت لتفعيل الحساب المساعد.",
    )
    return ConversationHandler.END


# ── معالج إعداد المساعد (CallbackQuery) ──
admin_assistant_handler = CallbackQueryHandler(
    admin_assistant_cb, pattern="^admin_assistant$"
)


# ══════════════════════════════════════════════════════════════════════════
# Fragment — التنفيذ اليدوي + الاسترداد
# ══════════════════════════════════════════════════════════════════════════

async def frag_done_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن ضغط ✅ تنفيذ يدوي — يُحدّث الطلب ويُخطر المستخدم."""
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫 غير مصرّح", show_alert=True)
    await q.answer("✅ تم")

    from db import get_fragment_order, update_fragment_order
    oid_str = q.data.replace("frag_done_", "")
    oid     = int(oid_str)
    order   = get_fragment_order(oid)

    update_fragment_order(oid, "success")
    await q.edit_message_text(
        q.message.text + "\n\n✅ <b>تم التنفيذ اليدوي</b>",
        parse_mode="HTML",
    )
    if order:
        icon = "✅" if order["svc"] == "premium" else "⭐"
        try:
            await ctx.bot.send_message(
                order["user_id"],
                f"✅ <b>تم تنفيذ طلبك بنجاح!</b>\n"
                f"{icon} {order['label']}\n"
                f"👤 <code>{order['username']}</code>\n"
                f"رقم الطلب: <b>#{oid}</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def frag_refund_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن ضغط ❌ استرداد — يرد الرصيد للمستخدم."""
    q   = update.callback_query
    uid = q.from_user.id
    if uid != ADMIN_ID:
        return await q.answer("🚫 غير مصرّح", show_alert=True)
    await q.answer("💸 تم الاسترداد")

    from db import get_fragment_order, update_fragment_order, add_balance
    oid_str = q.data.replace("frag_refund_", "")
    oid     = int(oid_str)
    order   = get_fragment_order(oid)

    if order and order["status"] not in ("refunded",):
        add_balance(order["user_id"], order["amount_usd"], f"استرداد طلب Fragment #{oid}", "استرداد")
        update_fragment_order(oid, "refunded")
        await q.edit_message_text(
            q.message.text + "\n\n💸 <b>تم الاسترداد للمستخدم</b>",
            parse_mode="HTML",
        )
        try:
            await ctx.bot.send_message(
                order["user_id"],
                f"💸 <b>تم استرداد مبلغ طلبك #{oid}</b>\n"
                f"<b>{order['amount_usd']:.4f}$</b> أُضيفت لرصيدك.",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await q.answer("⚠️ الطلب مُسترد بالفعل أو غير موجود", show_alert=True)


frag_done_handler   = CallbackQueryHandler(frag_done_cb,   pattern=r"^frag_done_\d+$")
frag_refund_handler = CallbackQueryHandler(frag_refund_cb, pattern=r"^frag_refund_\d+$")

# ── ConversationHandler — إعداد API ──
asst_api_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(asst_set_api_cb, pattern="^asst_set_api$")],
    states={
        WAIT_ASST_API: [MessageHandler(filters.TEXT & ~filters.COMMAND, asst_save_api)],
    },
    fallbacks=[CallbackQueryHandler(admin_assistant_cb, pattern="^admin_assistant$")],
    per_message=False,
)

# ── ConversationHandler — String Session ──
asst_session_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(asst_set_session_cb, pattern="^asst_set_session$")],
    states={
        WAIT_ASST_SESSION: [MessageHandler(filters.TEXT & ~filters.COMMAND, asst_save_session)],
    },
    fallbacks=[CallbackQueryHandler(admin_assistant_cb, pattern="^admin_assistant$")],
    per_message=False,
)


# ══════════════════════════════════════════════════════════════════
#  شحن سوا اليدوي — admin handles manual Sawa card approval
#  نظام dict عالمي بدلاً من ConversationHandler لضمان موثوقية الحالة
# ══════════════════════════════════════════════════════════════════

# admin_id → {oid, uid, card_id, code}
_sawa_pending: dict = {}


async def sawa_manual_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """أدمن يضغط ✅ شحن يدوي → يُخزَّن الطلب ويُطلب المبلغ."""
    from telegram import ForceReply
    q = update.callback_query
    await q.answer()

    # callback_data: sawa_d_{oid}_{uid}_{card_id}
    parts = q.data.split("_")
    try:
        oid     = int(parts[2])
        uid     = int(parts[3])
        card_id = int(parts[4])
    except (IndexError, ValueError):
        await q.edit_message_text("⚠️ بيانات غير صحيحة.")
        return

    from db import get_order
    order = get_order(oid)
    code  = "غير معروف"
    if order:
        p = (order.get("service") or "").split("|")
        if len(p) >= 2:
            code = p[1]

    admin_id = q.from_user.id
    _sawa_pending[admin_id] = {"oid": oid, "uid": uid, "card_id": card_id}

    await q.edit_message_text(
        f"✅ <b>شحن يدوي — طلب #{oid}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 معرّف المستخدم: <code>{uid}</code>\n"
        f"💳 كود البطاقة: <code>{code}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━",
        parse_mode="HTML",
    )
    await ctx.bot.send_message(
        admin_id,
        "💬 أرسل الآن <b>قيمة البطاقة بالريال السعودي</b> ليتم إضافتها للعميل:",
        parse_mode="HTML",
        reply_markup=ForceReply(selective=False, input_field_placeholder="مثال: 50"),
    )


async def sawa_amount_recv(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يستقبل مبلغ الريال من الأدمن ويُنفّذ الشحن اليدوي."""
    if not update.message or not update.message.text:
        return

    admin_id = update.message.from_user.id
    if admin_id not in _sawa_pending:
        return  # لا توجد عملية انتظار — تجاهل

    text = update.message.text.strip()
    try:
        amount_sar = float(text.replace(",", "."))
        if amount_sar <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ أرسل مبلغاً رقمياً صحيحاً موجباً (مثال: 50):"
        )
        return

    # استخراج البيانات وحذف الحالة
    data    = _sawa_pending.pop(admin_id)
    oid     = data["oid"]
    uid     = data["uid"]
    card_id = data["card_id"]

    from db import (
        get_card_rate, update_pending_card, add_card_loaded,
        add_balance, add_daily_usage, update_order_status,
    )

    rate       = get_card_rate("sawa")
    amount_usd = round(amount_sar * rate / 100, 4)

    update_pending_card(card_id, "approved", amount_usd)
    add_card_loaded(uid, "sawa", amount_usd)
    add_balance(uid, amount_usd, f"شحن بطاقة سوا {amount_sar:.0f}ر (يدوي)", "إيداع")
    add_daily_usage(uid, amount_usd)
    update_order_status(oid, "completed")

    log.info(f"✅ شحن سوا يدوي: oid={oid} uid={uid} {amount_sar}ر={amount_usd}$")

    # إشعار العميل
    try:
        await ctx.bot.send_message(
            uid,
            f"✅ <b>تم شحن بطاقة سوا بنجاح!</b>\n\n"
            f"💰 قيمة البطاقة: <b>{amount_sar:.0f} ريال</b>\n"
            f"📊 رصيد بطاقتك: <b>+{amount_usd:.2f}$</b>\n\n"
            f"<i>يمكنك طلب السحب من قسم شحن البطاقات.</i>",
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning(f"sawa_manual: لم يُرسل إشعار للعميل {uid}: {e}")

    await update.message.reply_text(
        f"✅ <b>تم الشحن اليدوي بنجاح!</b>\n\n"
        f"👤 المستخدم: <code>{uid}</code>\n"
        f"💰 القيمة: <b>{amount_sar:.0f} ريال → {amount_usd:.4f}$</b>\n"
        f"🔖 طلب #{oid} → مكتمل ✔️",
        parse_mode="HTML",
    )


async def sawa_manual_rej_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """أدمن يرفض الكرت → إبلاغ العميل."""
    q = update.callback_query
    await q.answer()

    parts = q.data.split("_")
    try:
        oid     = int(parts[2])
        uid     = int(parts[3])
        card_id = int(parts[4])
    except (IndexError, ValueError):
        await q.edit_message_text("⚠️ بيانات غير صحيحة.")
        return

    from db import update_pending_card, update_order_status
    update_pending_card(card_id, "rejected", 0)
    update_order_status(oid, "rejected")

    await q.edit_message_text(
        f"❌ <b>تم رفض الكرت — طلب #{oid}</b>\n"
        f"👤 المستخدم: <code>{uid}</code>",
        parse_mode="HTML",
    )

    try:
        await ctx.bot.send_message(
            uid,
            "❌ <b>عذراً، تعذر شحن بطاقة سوا.</b>\n\n"
            "البطاقة غير صالحة أو مستخدمة مسبقاً.\n"
            "تواصل مع الدعم إن كنت متأكداً من صحتها.",
            parse_mode="HTML",
        )
    except Exception as e:
        log.warning(f"sawa_manual_rej: لم يُرسل إشعار للعميل {uid}: {e}")

    # إزالة من الانتظار إن وجد
    _sawa_pending.pop(q.from_user.id, None)


# ── Handlers (بدون ConversationHandler) ──
sawa_manual_start_handler = CallbackQueryHandler(sawa_manual_start, pattern=r"^sawa_d_\d+_\d+_\d+$")
sawa_manual_rej_handler   = CallbackQueryHandler(sawa_manual_rej_cb, pattern=r"^sawa_r_\d+_\d+_\d+$")
sawa_amount_msg_handler   = MessageHandler(filters.TEXT & ~filters.COMMAND, sawa_amount_recv)


# ══════════════════════════════════════════════════════
# 💰 رصيد العملاء — صفحات
# ══════════════════════════════════════════════════════

_BAL_PER_PAGE = 15


async def admin_balances_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يعرض أول صفحة من رصيد العملاء."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    await _send_balances_page(q, ctx, 0, edit=True)


async def balances_page_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تنقل بين صفحات رصيد العملاء."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    page = int(q.data.split("_")[-1])
    await _send_balances_page(q, ctx, page, edit=True)


async def _send_balances_page(q, ctx, page: int, edit: bool = False):
    from db import get_users_balances_page, count_total_users
    total  = count_total_users()
    offset = page * _BAL_PER_PAGE
    users  = get_users_balances_page(offset, _BAL_PER_PAGE)

    lines = [f"💰 <b>رصيد العملاء</b> — صفحة {page+1} ({total} مستخدم)\n━━━━━━━━━━━━━━━━"]
    for i, u in enumerate(users, start=offset + 1):
        name  = (u.get("first_name") or "—")[:15]
        uname = f"@{u['username']}" if u.get("username") else "—"
        bal   = u.get("balance") or 0
        lines.append(f"{i}. {name} | {uname} | <code>{u['user_id']}</code> — <b>{bal:.4f}$</b>")

    if not users:
        lines.append("لا يوجد مستخدمون بعد.")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"bal_page_{page-1}"))
    if offset + _BAL_PER_PAGE < total:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"bal_page_{page+1}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 لوحة الأدمن", callback_data="admin_panel")])
    kb = InlineKeyboardMarkup(rows)

    text = "\n".join(lines)
    if edit:
        await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await q.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


admin_balances_handler  = CallbackQueryHandler(admin_balances_cb, pattern="^admin_balances$")
balances_page_handler   = CallbackQueryHandler(balances_page_cb,  pattern=r"^bal_page_\d+$")
