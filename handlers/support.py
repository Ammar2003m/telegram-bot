from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters
)

from config import ADMIN_ID
from db import (
    get_user, create_ticket, save_reply, get_user_tickets,
    get_ticket, close_ticket, is_banned
)
from keyboards import make_btn as MB, make_url_btn as URL_BTN, admin_edit_row

SUPPORT_HUMAN_URL = "http://t.me/aaamp"

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "— — — — — — — — — —"

WAIT_SUPPORT_MSG = 0
WAIT_REPLY_TEXT  = 0


# ═══════════════════════════════════════════════
# مساعدات مشتركة
# ═══════════════════════════════════════════════

def _support_menu_kb(uid: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [
            MB("📩 تذاكري",        "support_tickets", "btn_sup_tickets"),
            MB("✏️ تذكرة جديدة",   "new_ticket",      "btn_sup_new"),
        ],
        [URL_BTN("👤 الدعم البشري", SUPPORT_HUMAN_URL, "btn_sup_human")],
        [MB("🔙 القائمة الرئيسية", "main_menu",       "btn_sup_back_main")],
    ]
    rows += admin_edit_row("support_sec", uid)
    return InlineKeyboardMarkup(rows)


def _status_icon(status: str) -> str:
    return {"open": "🟡 مفتوحة", "closed": "✅ مُغلقة"}.get(status, status)


# ═══════════════════════════════════════════════
# جانب المستخدم — القائمة الرئيسية للدعم
# ═══════════════════════════════════════════════

async def support_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """نقطة الدخول — يعرض قائمة الدعم الفني"""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_banned(uid):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    await q.edit_message_text(
        f"{SEP}\n🛟 الدعم الفني\n{SEP2}\n"
        "اختر أحد الخيارات أدناه:\n\n"
        "📩 <b>تذاكري</b> — عرض تذاكرك السابقة والردود عليها\n"
        "✏️ <b>تذكرة جديدة</b> — فتح طلب دعم جديد\n"
        "👤 <b>الدعم البشري</b> — تواصل مباشر مع المالك",
        parse_mode="HTML",
        reply_markup=_support_menu_kb(uid),
    )


# ═══════════════════════════════════════════════
# عرض قائمة التذاكر
# ═══════════════════════════════════════════════

async def my_tickets_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يعرض تذاكر المستخدم كأزرار قابلة للنقر"""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    rows = get_user_tickets(uid, limit=10)
    if not rows:
        await q.edit_message_text(
            f"{SEP}\n📭 لا توجد تذاكر\n{SEP2}\n"
            "لم تفتح أي تذكرة دعم بعد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data="support")],
            ]),
        )
        return

    buttons = []
    for row in rows:
        icon = "🟡" if row["status"] == "open" else "✅"
        label = f"{icon} تذكرة #{row['id']}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"support_ticket_{row['id']}")])

    buttons.append([MB("🔙 رجوع", "support", "btn_sup_back")])

    await q.edit_message_text(
        f"{SEP}\n📩 تذاكري\n{SEP2}\n"
        "اضغط على التذكرة لعرض تفاصيلها:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


# ═══════════════════════════════════════════════
# عرض تفاصيل تذكرة واحدة
# ═══════════════════════════════════════════════

async def ticket_detail_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """يعرض محتوى التذكرة + زر رجوع"""
    q = update.callback_query
    await q.answer()

    ticket_id = int(q.data.split("_")[-1])
    ticket = get_ticket(ticket_id)

    if not ticket or ticket["user_id"] != q.from_user.id:
        await q.answer("❌ التذكرة غير موجودة", show_alert=True)
        return

    status_text = _status_icon(ticket["status"])
    reply_block = (
        f"\n📥 <b>رد الدعم:</b>\n{ticket['reply']}"
        if ticket["reply"]
        else "\n⏳ <i>في انتظار الرد من فريق الدعم…</i>"
    )

    await q.edit_message_text(
        f"{SEP}\n🎫 التذكرة #{ticket_id} — {status_text}\n{SEP2}\n"
        f"📤 <b>رسالتك:</b>\n{ticket['message']}"
        f"{reply_block}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [MB("🔙 رجوع للتذاكر", "support_tickets", "btn_sup_tix_back")],
        ]),
    )


# ═══════════════════════════════════════════════
# فتح تذكرة جديدة (محادثة)
# ═══════════════════════════════════════════════

async def new_ticket_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن يبدأ محادثة جديدة"""
    q = update.callback_query
    await q.answer()
    if is_banned(q.from_user.id):
        return await q.answer("🚫 أنت محظور", show_alert=True)

    await q.edit_message_text(
        f"{SEP}\n✏️ تذكرة جديدة\n{SEP2}\n"
        "اكتب رسالتك وسيقوم فريق الدعم بالرد عليك في أقرب وقت.\n\n"
        "💡 <i>صِف مشكلتك بوضوح لنتمكن من مساعدتك بشكل أسرع.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [MB("❌ إلغاء", "support_cancel", "btn_sup_cancel")],
        ]),
    )
    return WAIT_SUPPORT_MSG


async def handle_support_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """استقبال رسالة المستخدم وإنشاء التذكرة"""
    uid  = update.effective_user.id
    text = update.message.text.strip()

    ticket_id = create_ticket(uid, text)

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✉️ رد",       callback_data=f"reply_ticket_{ticket_id}"),
            InlineKeyboardButton("🔒 إغلاق",    callback_data=f"close_ticket_{ticket_id}"),
        ]
    ])
    name = update.effective_user.full_name
    await ctx.bot.send_message(
        ADMIN_ID,
        f"{SEP}\n📩 تذكرة دعم جديدة #{ticket_id}\n{SEP2}\n"
        f"👤 <b>{name}</b> | <code>{uid}</code>\n\n"
        f"💬 {text}",
        reply_markup=kb,
        parse_mode="HTML"
    )

    await update.message.reply_text(
        f"{SEP}\n✅ تم إرسال تذكرتك\n{SEP2}\n"
        f"رقم التذكرة: <b>#{ticket_id}</b>\n"
        f"سيتم الرد عليك قريباً.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 عرض تذاكري", callback_data="support_tickets")],
            [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
        ]),
    )
    return ConversationHandler.END


async def cancel_new_ticket(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إلغاء فتح تذكرة — يعود لقائمة الدعم"""
    if update.callback_query:
        q = update.callback_query
        await q.answer()
        await q.edit_message_text(
            f"{SEP}\n🛟 الدعم الفني\n{SEP2}\n"
            "اختر أحد الخيارات أدناه:\n\n"
            "📩 <b>تذاكري</b> — عرض تذاكرك السابقة والردود عليها\n"
            "✏️ <b>تذكرة جديدة</b> — فتح طلب دعم جديد",
            parse_mode="HTML",
            reply_markup=_support_menu_kb(),
        )
    else:
        await update.message.reply_text(
            "تم الإلغاء.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛟 الدعم الفني", callback_data="support")],
            ]),
        )
    return ConversationHandler.END


# ═══════════════════════════════════════════════
# جانب الأدمن — الرد على التذاكر
# ═══════════════════════════════════════════════

async def admin_reply_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن يضغط زر رد"""
    q = update.callback_query
    await q.answer()

    ticket_id = int(q.data.split("_")[-1])
    ticket    = get_ticket(ticket_id)

    if not ticket:
        return await q.answer("❌ التذكرة غير موجودة", show_alert=True)

    if ticket["status"] == "closed":
        return await q.answer("⚠️ هذه التذكرة مُغلقة مسبقاً", show_alert=True)

    ctx.user_data["reply_ticket_id"] = ticket_id
    await q.message.reply_text(
        f"{SEP}\n✉️ الرد على التذكرة #{ticket_id}\n{SEP2}\n"
        f"👤 المستخدم: <code>{ticket['user_id']}</code>\n\n"
        f"💬 رسالته:\n{ticket['message']}\n\n"
        f"اكتب ردك الآن:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="cancel_reply")],
        ]),
    )
    return WAIT_REPLY_TEXT


async def save_admin_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """حفظ الرد وإشعار المستخدم"""
    ticket_id = ctx.user_data.pop("reply_ticket_id", None)
    if not ticket_id:
        return ConversationHandler.END

    reply   = update.message.text.strip()
    user_id = save_reply(ticket_id, reply)

    if user_id:
        await ctx.bot.send_message(
            user_id,
            f"{SEP}\n📬 رد من فريق الدعم\n{SEP2}\n"
            f"تم الرد على تذكرتك رقم <b>#{ticket_id}</b>.\n\n"
            f"📥 الرد:\n{reply}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 عرض التذكرة", callback_data=f"support_ticket_{ticket_id}")],
            ]),
            parse_mode="HTML"
        )

    await update.message.reply_text(
        f"✅ تم إرسال الرد على التذكرة #{ticket_id}.",
        parse_mode="HTML"
    )
    return ConversationHandler.END


async def admin_close_ticket_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الأدمن يُغلق التذكرة بدون رد"""
    q = update.callback_query
    await q.answer()

    ticket_id = int(q.data.split("_")[-1])
    ticket    = get_ticket(ticket_id)

    if not ticket:
        return await q.answer("❌ التذكرة غير موجودة", show_alert=True)

    if ticket["status"] == "closed":
        return await q.answer("⚠️ التذكرة مُغلقة مسبقاً", show_alert=True)

    close_ticket(ticket_id)

    try:
        await ctx.bot.send_message(
            ticket["user_id"],
            f"{SEP}\n🔒 تم إغلاق تذكرتك\n{SEP2}\n"
            f"تذكرتك رقم <b>#{ticket_id}</b> تم إغلاقها من قِبل فريق الدعم.\n"
            f"إذا كان لديك استفسار آخر يمكنك فتح تذكرة جديدة.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🛟 الدعم الفني", callback_data="support")],
            ]),
        )
    except Exception:
        pass

    await q.edit_message_reply_markup(
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ مُغلقة #{ticket_id}", callback_data="noop")],
        ])
    )
    await q.message.reply_text(f"🔒 تم إغلاق التذكرة #{ticket_id}.")


async def cancel_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """إلغاء رد الأدمن"""
    ctx.user_data.pop("reply_ticket_id", None)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("تم الإلغاء.")
    else:
        await update.message.reply_text("تم الإلغاء.")
    return ConversationHandler.END


async def noop_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()


# ═══════════════════════════════════════════════
# تجميع الـ handlers
# ═══════════════════════════════════════════════

support_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(new_ticket_start, pattern="^new_ticket$")],
    states={
        WAIT_SUPPORT_MSG: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_support_message),
            CallbackQueryHandler(cancel_new_ticket, pattern="^support_cancel$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_new_ticket, pattern="^support_cancel$"),
        MessageHandler(filters.COMMAND, cancel_new_ticket),
    ],
    per_message=False,
    allow_reentry=True,
)

admin_reply_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(admin_reply_start, pattern="^reply_ticket_\\d+$")],
    states={
        WAIT_REPLY_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_admin_reply),
            CallbackQueryHandler(cancel_reply, pattern="^cancel_reply$"),
        ],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_reply, pattern="^cancel_reply$"),
        MessageHandler(filters.COMMAND, cancel_reply),
    ],
    per_message=False,
    allow_reentry=True,
)

support_menu_handler     = CallbackQueryHandler(support_menu,           pattern="^support$")
my_tickets_handler       = CallbackQueryHandler(my_tickets_cb,          pattern="^support_tickets$")
ticket_detail_handler    = CallbackQueryHandler(ticket_detail_cb,       pattern="^support_ticket_\\d+$")
admin_close_handler      = CallbackQueryHandler(admin_close_ticket_cb,  pattern="^close_ticket_\\d+$")
noop_handler             = CallbackQueryHandler(noop_cb,                pattern="^noop$")
