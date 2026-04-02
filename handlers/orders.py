"""
📦 نظام إدارة الطلبات — جانب المستخدم
══════════════════════════════════════
• سجل الطلبات مع تفاصيل كل طلب
• تتبع حالة الطلب
• إعادة آخر طلب
• الخدمات الأكثر طلباً
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler, ContextTypes

from keyboards import back, make_btn as MB, admin_edit_row
from db import (
    get_user, get_user_orders, get_order, get_last_order,
    get_popular_services, create_order, deduct_balance,
    get_balance, convert_from_usd, is_banned,
)
from config import CURRENCY_SYMBOLS

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — —"

_STATUS_ICON = {
    "pending":   "⏳",
    "completed": "✅",
    "done":      "✅",
    "cancelled": "❌",
    "canceled":  "❌",
}
_STATUS_AR = {
    "pending":   "قيد التنفيذ",
    "completed": "مكتمل",
    "done":      "مكتمل",
    "cancelled": "ملغي",
    "canceled":  "ملغي",
}


# ════════════════════════════════════════════════════════
# سجل الطلبات المحسّن
# ════════════════════════════════════════════════════════

async def my_orders_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    rows = get_user_orders(uid)
    if not rows:
        await q.edit_message_text(
            f"{SEP}\n📭 طلباتك\n{SEP}\n\n"
            "لا يوجد طلبات حتى الآن.\n"
            "ابدأ بشراء أي خدمة من القائمة!",
            reply_markup=back(),
        )
        return

    lines = [f"{SEP}\n🛍 <b>آخر طلباتك</b>\n{SEP}\n"]
    rows_kb = []
    for o in rows:
        icon = _STATUS_ICON.get(o["status"], "❓")
        ar   = _STATUS_AR.get(o["status"], o["status"])
        lines.append(f"{icon} <b>#{o['id']}</b>  {o['service']}\n    💲 {o['amount']:.2f}$  |  {ar}")
        rows_kb.append([InlineKeyboardButton(
            f"{icon} #{o['id']} — {o['service'][:20]}",
            callback_data=f"order_detail_{o['id']}"
        )])

    rows_kb.append([
        MB("🔁 إعادة آخر طلب", "reorder",          "btn_orders_reorder"),
        MB("🔥 الأكثر طلباً",   "popular_services",  "btn_orders_popular"),
    ])
    rows_kb.append([MB("🔙 رجوع", "main_menu", "btn_back_main")])
    rows_kb += admin_edit_row("orders_sec", uid)

    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(rows_kb),
        parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════
# تفاصيل طلب واحد
# ════════════════════════════════════════════════════════

async def order_detail_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id

    oid   = int(q.data.replace("order_detail_", ""))
    order = get_order(oid)

    if not order or order["user_id"] != uid:
        await q.answer("❌ الطلب غير موجود", show_alert=True)
        return

    icon   = _STATUS_ICON.get(order["status"], "❓")
    status = _STATUS_AR.get(order["status"],   order["status"])

    msg = (
        f"{SEP}\n📦 <b>تفاصيل الطلب #{oid}</b>\n{SEP}\n\n"
        f"⚙️ <b>الخدمة:</b>  {order['service']}\n"
        f"📝 <b>البيانات:</b> {order['details']}\n"
        f"💲 <b>المبلغ:</b>  {order['amount']:.4f}$\n"
        f"{icon} <b>الحالة:</b>  {status}\n"
        f"🕐 <b>التاريخ:</b> {str(order['created_at'])[:16]}\n"
    )

    kb = InlineKeyboardMarkup([
        [MB("🔁 إعادة هذا الطلب", f"reorder_id_{oid}", "btn_orders_reorder")],
        [MB("🔙 رجوع للطلبات",    "orders",             "btn_back")],
    ])
    await q.edit_message_text(msg, reply_markup=kb, parse_mode="HTML")


# ════════════════════════════════════════════════════════
# إعادة آخر طلب — عرض التأكيد
# ════════════════════════════════════════════════════════

async def reorder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    last = get_last_order(uid)
    if not last:
        await q.answer("لا يوجد طلب سابق للإعادة.", show_alert=True)
        return

    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    local    = convert_from_usd(last["amount"], currency)
    icon     = _STATUS_ICON.get(last["status"], "❓")

    msg = (
        f"{SEP}\n🔁 <b>إعادة الطلب</b>\n{SEP}\n\n"
        f"⚙️ <b>الخدمة:</b>  {last['service']}\n"
        f"📝 <b>البيانات:</b> {last['details']}\n"
        f"💲 <b>السعر:</b>  {local:.2f} {sym}\n"
        f"{icon} <b>الحالة الأصلية:</b> {_STATUS_AR.get(last['status'], last['status'])}\n\n"
        f"هل تريد إعادة هذا الطلب؟"
    )
    kb = InlineKeyboardMarkup([
        [
            MB("✅ تأكيد الإعادة", f"reorder_id_{last['id']}", "btn_confirm"),
            MB("❌ إلغاء",          "orders",                   "btn_cancel"),
        ]
    ])
    await q.edit_message_text(msg, reply_markup=kb, parse_mode="HTML")


# ════════════════════════════════════════════════════════
# إعادة طلب بـ ID محدد — تنفيذ
# ════════════════════════════════════════════════════════

async def reorder_by_id_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    oid   = int(q.data.replace("reorder_id_", ""))
    order = get_order(oid)

    if not order or order["user_id"] != uid:
        await q.answer("❌ الطلب غير موجود", show_alert=True)
        return

    user     = get_user(uid)
    currency = user["currency"] if user else "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)
    usd      = order["amount"]
    local    = convert_from_usd(usd, currency)
    balance  = get_balance(uid)

    if balance < usd:
        bal_local = convert_from_usd(balance, currency)
        await q.edit_message_text(
            f"{SEP}\n❌ رصيد غير كافٍ\n{SEP}\n\n"
            f"💰 رصيدك: <b>{bal_local:.2f} {sym}</b>\n"
            f"💲 المطلوب: <b>{local:.2f} {sym}</b>\n\n"
            "يرجى شحن رصيدك أولاً.",
            reply_markup=InlineKeyboardMarkup([
                [MB("💳 شحن الرصيد",   "deposit", "btn_charge")],
                [MB("🔙 رجوع للطلبات", "orders",  "btn_back")],
            ]),
            parse_mode="HTML",
        )
        return

    deduct_balance(uid, usd, f"إعادة طلب: {order['service']}")
    new_oid = create_order(uid, order["service"], order["details"], usd)

    # إشعار الأدمن
    from config import ADMIN_ID
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🔁 <b>إعادة طلب — #{new_oid}</b>\n"
            f"👤 <code>{uid}</code>\n"
            f"⚙️ {order['service']}\n"
            f"📝 {order['details']}\n"
            f"💲 {usd:.4f}$",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ تم",    callback_data=f"done_{new_oid}"),
                InlineKeyboardButton("❌ إلغاء", callback_data=f"cancel_{new_oid}"),
            ]]),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await q.edit_message_text(
        f"{SEP}\n✅ تم إعادة الطلب\n{SEP}\n\n"
        f"⚙️ <b>{order['service']}</b>\n"
        f"📝 {order['details']}\n"
        f"💲 {local:.2f} {sym}\n"
        f"رقم الطلب الجديد: <b>#{new_oid}</b>\n\n"
        f"⏳ سيتم التنفيذ قريباً.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 سجل الطلبات", callback_data="orders")],
        ]),
        parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════
# الأكثر طلباً
# ════════════════════════════════════════════════════════

async def popular_services_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    rows = get_popular_services(8)
    if not rows:
        await q.answer("لا يوجد بيانات كافية بعد.", show_alert=True)
        return

    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    lines  = [f"{SEP}\n🔥 <b>الخدمات الأكثر طلباً</b>\n{SEP}\n"]
    for i, row in enumerate(rows):
        medal = medals[i] if i < len(medals) else f"{i+1}."
        lines.append(f"{medal}  {row['service']} — <b>{row['total']}</b> طلب")

    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع للطلبات", callback_data="orders")],
        ]),
        parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════
# تسجيل الهاندلرز
# ════════════════════════════════════════════════════════

my_orders_handler       = CallbackQueryHandler(my_orders_cb,       pattern="^orders$")
order_detail_handler    = CallbackQueryHandler(order_detail_cb,    pattern="^order_detail_")
reorder_handler         = CallbackQueryHandler(reorder_cb,         pattern="^reorder$")
reorder_by_id_handler   = CallbackQueryHandler(reorder_by_id_cb,   pattern="^reorder_id_")
popular_services_handler= CallbackQueryHandler(popular_services_cb,pattern="^popular_services$")