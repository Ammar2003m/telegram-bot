from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

from config import ADMIN_ID
from db import (
    add_reply_button, get_reply_buttons,
    delete_reply_button, build_inline_keyboard
)

# ── حالات المحادثة ──────────────────────────────
RB_TEXT  = 18
RB_COLOR = 19
RB_URL   = 20

COLOR_PREFIX = {"blue": "🟦", "green": "🟩", "red": "🟥"}
COLOR_LABELS = {
    "blue":  "🟦 أزرق — زر عادي",
    "green": "🟩 أخضر — زر رابط (URL)",
    "red":   "🟥 أحمر — زر رابط (URL)",
}


def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID


# ════════════════════════════════════════════════
# قائمة إدارة الأزرار الشفافة
# ════════════════════════════════════════════════

async def admin_rb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    count = len(get_reply_buttons())
    # معاينة الكيبورد الحالي
    custom_kb = build_inline_keyboard()
    preview = "\n\n<b>📌 معاينة الأزرار الحالية:</b>" if custom_kb else ""

    info_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة زر",       callback_data="rb_add")],
        [InlineKeyboardButton("📋 عرض الأزرار",    callback_data="rb_list")],
        [InlineKeyboardButton("🔙 رجوع",           callback_data="admin_panel")],
    ])
    await q.edit_message_text(
        f"⌨️ <b>الأزرار الشفافة الديناميكية</b>\n\n"
        f"📦 الأزرار الحالية: <b>{count}</b>\n\n"
        f"هذه أزرار شفافة (Inline) تظهر مدمجة داخل رسائل البوت.\n\n"
        f"<b>أنواع الألوان:</b>\n"
        f"🟦 أزرق = زر عادي (يظهر رسالة عند الضغط)\n"
        f"🟩 أخضر = زر رابط (يفتح رابط خارجي)\n"
        f"🟥 أحمر = زر رابط (يفتح رابط خارجي){preview}",
        reply_markup=info_kb,
        parse_mode="HTML"
    )


# ════════════════════════════════════════════════
# خطوات إضافة زر جديد
# ════════════════════════════════════════════════

async def start_add_rb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 0: بدء إضافة زر → اطلب النص."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END
    await q.edit_message_text(
        "✏️ <b>إضافة زر شفاف جديد</b>\n\n"
        "أرسل نص الزر:\n\n"
        "✨ <i>يمكنك استخدام Premium Emoji في النص</i>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 إلغاء", callback_data="rb_menu")]
        ]),
        parse_mode="HTML"
    )
    return RB_TEXT


async def get_rb_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 1: استقبال النص → اختيار اللون."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    msg       = update.message
    text      = (msg.text or "").strip()
    text_html = (msg.text_html or text).strip()

    if not text:
        await msg.reply_text("⚠️ أرسل نصاً.")
        return RB_TEXT

    emoji_id = None
    if msg.entities:
        for ent in msg.entities:
            if ent.type == "custom_emoji":
                emoji_id = ent.custom_emoji_id
                break

    ctx.user_data["rb_text"]      = text
    ctx.user_data["rb_text_html"] = text_html
    ctx.user_data["rb_emoji_id"]  = emoji_id or ""

    try:
        await msg.delete()
    except Exception:
        pass

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🟦 أزرق",  callback_data="rbcolor_blue"),
            InlineKeyboardButton("🟩 أخضر",  callback_data="rbcolor_green"),
            InlineKeyboardButton("🟥 أحمر",  callback_data="rbcolor_red"),
        ],
        [InlineKeyboardButton("🔙 إلغاء", callback_data="rb_menu")],
    ])
    await msg.reply_text(
        f"✅ النص: <code>{text}</code>\n\n"
        f"🎨 <b>اختر لون الزر الشفاف:</b>\n\n"
        f"🟦 أزرق — زر عادي (لا يحتاج رابط)\n"
        f"🟩 أخضر — زر رابط (يحتاج رابط)\n"
        f"🟥 أحمر — زر رابط (يحتاج رابط)",
        reply_markup=kb,
        parse_mode="HTML"
    )
    return RB_COLOR


async def get_rb_color(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 2: استقبال اللون."""
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return ConversationHandler.END

    color = q.data.split("_")[1]
    ctx.user_data["rb_color"] = color

    if color in ("green", "red"):
        await q.edit_message_text(
            f"🔗 <b>أدخل رابط الزر {'الأخضر' if color == 'green' else 'الأحمر'}</b>:\n\n"
            f"<i>مثال: https://example.com</i>\n"
            f"⚠️ يجب أن يبدأ الرابط بـ https://",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 إلغاء", callback_data="rb_menu")]
            ]),
            parse_mode="HTML"
        )
        return RB_URL

    # أزرق → احفظ بدون رابط
    await _do_save_rb(q, ctx, url="")
    return ConversationHandler.END


async def get_rb_url(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """الخطوة 3: استقبال URL."""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    url = (update.message.text or "").strip()
    if not (url.startswith("https://") or url.startswith("http://")):
        await update.message.reply_text(
            "⚠️ يجب أن يبدأ الرابط بـ https:// أو http://\nأرسله مجدداً:"
        )
        return RB_URL

    try:
        await update.message.delete()
    except Exception:
        pass

    await _do_save_rb(update.message, ctx, url=url)
    return ConversationHandler.END


async def _do_save_rb(msg_or_q, ctx: ContextTypes.DEFAULT_TYPE, url: str):
    """حفظ الزر في DB وإظهار التأكيد."""
    text      = ctx.user_data.pop("rb_text",      "")
    text_html = ctx.user_data.pop("rb_text_html", text)
    emoji_id  = ctx.user_data.pop("rb_emoji_id",  "")
    color     = ctx.user_data.pop("rb_color",     "blue")

    add_reply_button(text, text_html, color, url, emoji_id)

    label  = COLOR_LABELS.get(color, color)
    prefix = COLOR_PREFIX.get(color, "")
    body = (
        f"✅ <b>تم إضافة الزر الشفاف!</b>\n\n"
        f"📝 النص: {prefix} <code>{text}</code>\n"
        f"🎨 النوع: {label}"
    )
    if url:
        body += f"\n🔗 الرابط: {url}"

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ إضافة آخر",   callback_data="rb_add")],
        [InlineKeyboardButton("📋 عرض الأزرار", callback_data="rb_list")],
        [InlineKeyboardButton("🔙 القائمة",      callback_data="rb_menu")],
    ])

    if hasattr(msg_or_q, "edit_message_text"):
        await msg_or_q.edit_message_text(body, reply_markup=kb, parse_mode="HTML")
    else:
        await msg_or_q.reply_text(body, reply_markup=kb, parse_mode="HTML")


# ════════════════════════════════════════════════
# عرض وحذف الأزرار
# ════════════════════════════════════════════════

async def list_rb_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    buttons = get_reply_buttons()
    if not buttons:
        await q.edit_message_text(
            "⌨️ لا يوجد أزرار شفافة بعد.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ إضافة زر", callback_data="rb_add")],
                [InlineKeyboardButton("🔙 رجوع",     callback_data="rb_menu")],
            ])
        )
        return

    lines = ["⌨️ <b>الأزرار الشفافة الحالية</b>\n"]
    del_rows = []
    for btn in buttons:
        prefix = COLOR_PREFIX.get(btn["color"], "⬜")
        extra  = f"\n   🔗 {btn['url']}" if btn["url"] else ""
        lines.append(f"{prefix} {btn['text_html']}{extra}")
        del_rows.append([InlineKeyboardButton(
            f"🗑 حذف: {btn['text'][:30]}",
            callback_data=f"rbd_{btn['id']}"
        )])

    del_rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="rb_menu")])
    lines.append("\n<i>اضغط على زر الحذف لإزالة الزر:</i>")

    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(del_rows),
        parse_mode="HTML"
    )


async def del_rb_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not is_admin(q.from_user.id):
        return
    bid = int(q.data.split("_")[1])
    delete_reply_button(bid)
    await q.answer("✅ تم الحذف", show_alert=True)
    await list_rb_cb(update, ctx)


# ════════════════════════════════════════════════
# معالجة ضغط الأزرار الشفافة من المستخدمين
# ════════════════════════════════════════════════

async def custom_btn_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """عند ضغط المستخدم على زر شفاف → أظهر نص الزر كتنبيه."""
    q = update.callback_query
    bid = int(q.data.split("_")[1])
    buttons = get_reply_buttons()
    btn = next((b for b in buttons if b["id"] == bid), None)
    if btn:
        await q.answer(btn["text"], show_alert=True)
    else:
        await q.answer("⚠️ الزر غير موجود", show_alert=True)


# ════════════════════════════════════════════════
# تجميع الـ handlers
# ════════════════════════════════════════════════

add_rb_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_rb, pattern="^rb_add$")],
    states={
        RB_TEXT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rb_text)],
        RB_COLOR: [CallbackQueryHandler(get_rb_color, pattern="^rbcolor_")],
        RB_URL:   [MessageHandler(filters.TEXT & ~filters.COMMAND, get_rb_url)],
    },
    fallbacks=[CallbackQueryHandler(lambda u, c: ConversationHandler.END, pattern="^rb_menu$")],
    per_message=False,
)

admin_rb_handler  = CallbackQueryHandler(admin_rb_menu,  pattern="^rb_menu$")
list_rb_handler   = CallbackQueryHandler(list_rb_cb,     pattern="^rb_list$")
del_rb_handler    = CallbackQueryHandler(del_rb_cb,      pattern="^rbd_")
custom_btn_handler = CallbackQueryHandler(custom_btn_cb, pattern="^custombtn_")
