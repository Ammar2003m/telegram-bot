"""
✏️ محرر الأزرار الشفافة الشامل
══════════════════════════════════
• 6 أقسام: الرئيسية، الخدمات، تيليجرام، العامة، الإيداع، التنقل
• تعديل نص + ملصق مميز + لون لكل زر
"""

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, MessageEntity
from telegram.ext import (
    CallbackQueryHandler, MessageHandler, ConversationHandler,
    ContextTypes, filters,
)

from config import ADMIN_ID
from db import (
    get_btn_color,    set_btn_color,
    get_btn_label,    set_btn_label,
    get_btn_emoji_id, set_btn_emoji_id,
    get_default_label,
    get_all_btn_settings,
    BTN_COLOR_NAMES, BUTTON_SECTIONS, ALL_BTNS,
)

EDIT_BTN_TEXT  = 21
EDIT_BTN_EMOJI = 22

_COLOR_ICON = {0: "⬜", 1: "🟩", 2: "🟦", 3: "🟥"}

def _is_admin(uid): return uid == ADMIN_ID
def _current_label(key): return get_btn_label(key, get_default_label(key))


# ════════════════════════════════════════════════════════
# مساعد مشترك: يرسم صفحة تعديل زر واحد (بدون q.data)
# ════════════════════════════════════════════════════════

async def _show_pick(key: str, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q            = update.callback_query
    default_text = get_default_label(key)
    label        = _current_label(key)
    color        = get_btn_color(key)
    emoji_id     = get_btn_emoji_id(key)

    emoji_line = f"<code>{emoji_id}</code>" if emoji_id else "لا يوجد"
    color_line = _COLOR_ICON.get(color, "⬜") + " " + BTN_COLOR_NAMES.get(color, "افتراضي")

    msg = (
        f"✏️ <b>تعديل الزر</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>النص الحالي:</b> {label}\n"
        f"🔤 <b>الافتراضي:</b>   {default_text}\n"
        f"🌟 <b>الإيموجي:</b>    {emoji_line}\n"
        f"🎨 <b>اللون:</b>       {color_line}\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )

    def cn(n):
        mk = "✅ " if color == n else ""
        return mk + {0: "⬜", 1: "🟩", 2: "🟦", 3: "🟥"}[n]

    sec_key = ALL_BTNS.get(key, ("", ""))[0]
    rows = [
        [
            InlineKeyboardButton("✏️ تعديل النص",            callback_data=f"bedit_text_{key}"),
            InlineKeyboardButton("🔁 إعادة الافتراضي",        callback_data=f"bedit_reset_{key}"),
        ],
        [
            InlineKeyboardButton("🌟 إضافة / تغيير الإيموجي", callback_data=f"bedit_emoji_{key}"),
            InlineKeyboardButton("🗑 حذف الإيموجي",            callback_data=f"bedit_delemoji_{key}"),
        ],
        [
            InlineKeyboardButton(cn(0) + " افتراضي", callback_data=f"bedit_color_{key}_0"),
            InlineKeyboardButton(cn(1) + " أخضر",    callback_data=f"bedit_color_{key}_1"),
        ],
        [
            InlineKeyboardButton(cn(2) + " أزرق",    callback_data=f"bedit_color_{key}_2"),
            InlineKeyboardButton(cn(3) + " أحمر",    callback_data=f"bedit_color_{key}_3"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data=f"bedit_sec_{sec_key}")],
    ]
    await q.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")


# ════════════════════════════════════════════════════════
# 1. الصفحة الرئيسية — اختيار القسم
# ════════════════════════════════════════════════════════

async def admin_btn_colors_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id): return

    rows = []
    for sec_key, sec_name in BUTTON_SECTIONS.items():
        count = sum(1 for v in ALL_BTNS.values() if v[0] == sec_key)
        rows.append([InlineKeyboardButton(
            f"{sec_name}  ({count} زر)",
            callback_data=f"bedit_sec_{sec_key}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع للوحة", callback_data="admin_panel")])

    await q.edit_message_text(
        "✏️ <b>محرر الأزرار الشفافة</b>\n\n"
        "اختر القسم الذي تريد تعديل أزراره:",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════
# 2. أزرار القسم المحدد
# ════════════════════════════════════════════════════════

async def bedit_section(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id): return

    sec_key  = q.data.replace("bedit_sec_", "")
    sec_name = BUTTON_SECTIONS.get(sec_key, sec_key)
    settings = get_all_btn_settings()

    rows = []
    for key, (section, default) in ALL_BTNS.items():
        if section != sec_key:
            continue
        s        = settings.get(key, {})
        label    = s.get("label") or default
        color    = s.get("color", 0)
        has_em   = bool(s.get("emoji_id"))
        em_tag   = "🌟" if has_em else ""
        clr_icon = _COLOR_ICON.get(color, "⬜")
        rows.append([InlineKeyboardButton(
            f"{clr_icon}{em_tag} {label}",
            callback_data=f"bedit_pick_{key}"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_btn_colors")])

    await q.edit_message_text(
        f"✏️ <b>{sec_name}</b>\n\n"
        "اضغط على الزر الذي تريد تعديله:\n\n"
        "🌟 = يوجد إيموجي  |  ⬜🟩🟦🟥 = اللون",
        reply_markup=InlineKeyboardMarkup(rows),
        parse_mode="HTML",
    )


# ════════════════════════════════════════════════════════
# 3. صفحة تعديل زر واحد
# ════════════════════════════════════════════════════════

async def bedit_pick(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id): return
    key = q.data.replace("bedit_pick_", "")
    await _show_pick(key, update, ctx)


# ════════════════════════════════════════════════════════
# تغيير اللون (فوري)
# ════════════════════════════════════════════════════════

async def bedit_color(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer(); return
    parts      = q.data.replace("bedit_color_", "").rsplit("_", 1)
    key, color = parts[0], int(parts[1])
    set_btn_color(key, color)
    await q.answer(f"✅ تم تغيير اللون إلى {BTN_COLOR_NAMES.get(color, '')}")
    await _show_pick(key, update, ctx)


# ════════════════════════════════════════════════════════
# حذف الإيموجي (فوري)
# ════════════════════════════════════════════════════════

async def bedit_delemoji(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer(); return
    key = q.data.replace("bedit_delemoji_", "")
    set_btn_emoji_id(key, "")
    await q.answer("🗑 تم حذف الإيموجي")
    await _show_pick(key, update, ctx)


# ════════════════════════════════════════════════════════
# إعادة النص الافتراضي (فوري)
# ════════════════════════════════════════════════════════

async def bedit_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_admin(q.from_user.id):
        await q.answer(); return
    key = q.data.replace("bedit_reset_", "")
    set_btn_label(key, "")
    await q.answer("🔁 تم إعادة النص الافتراضي")
    await _show_pick(key, update, ctx)


# ════════════════════════════════════════════════════════
# تعديل النص — محادثة
# ════════════════════════════════════════════════════════

async def bedit_text_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id): return
    key = q.data.replace("bedit_text_", "")
    ctx.user_data["bedit_key"] = key
    current = _current_label(key)
    await q.edit_message_text(
        f"✏️ <b>تعديل نص الزر</b>\n\n"
        f"النص الحالي: <b>{current}</b>\n\n"
        f"أرسل النص الجديد الآن:\n"
        f"<i>(يدعم الإيموجي العادية)</i>\n\n"
        f"/cancel للإلغاء",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data=f"bedit_cancel_{key}")
        ]]),
        parse_mode="HTML",
    )
    return EDIT_BTN_TEXT


async def bedit_text_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    key  = ctx.user_data.get("bedit_key", "")
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("⚠️ النص لا يمكن أن يكون فارغاً، أرسل مجدداً:")
        return EDIT_BTN_TEXT
    set_btn_label(key, text)
    await update.message.reply_text(
        f"✅ <b>تم تحديث نص الزر</b>\n\n"
        f"الزر: {get_default_label(key)}\n"
        f"النص الجديد: <b>{text}</b>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع لتعديل الزر", callback_data=f"bedit_pick_{key}")
        ]]),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════
# إضافة إيموجي مميز — محادثة
# ════════════════════════════════════════════════════════

async def bedit_emoji_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not _is_admin(q.from_user.id): return
    key = q.data.replace("bedit_emoji_", "")
    ctx.user_data["bedit_key"] = key
    cur_em = get_btn_emoji_id(key)
    await q.edit_message_text(
        f"🌟 <b>إضافة إيموجي مميز</b>\n\n"
        f"{'الإيموجي الحالي: <code>' + cur_em + '</code>' if cur_em else 'لا يوجد إيموجي حالياً'}\n\n"
        f"أرسل رسالة تحتوي على <b>إيموجي Premium متحرك</b>.\n\n"
        f"💡 <i>يظهر بجانب نص الزر.</i>\n\n"
        f"/cancel للإلغاء",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ إلغاء", callback_data=f"bedit_cancel_{key}")
        ]]),
        parse_mode="HTML",
    )
    return EDIT_BTN_EMOJI


async def bedit_emoji_receive(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.effective_user.id):
        return ConversationHandler.END
    key      = ctx.user_data.get("bedit_key", "")
    msg      = update.message
    entities = msg.entities or msg.caption_entities or []
    emoji_id = next(
        (e.custom_emoji_id for e in entities if e.type == MessageEntity.CUSTOM_EMOJI),
        None
    )
    if not emoji_id:
        await msg.reply_text(
            "⚠️ لم أجد إيموجي مميزاً.\n"
            "أرسل إيموجي Premium متحركاً (يحتاج اشتراك تيليجرام بريميوم)."
        )
        return EDIT_BTN_EMOJI
    set_btn_emoji_id(key, emoji_id)
    await msg.reply_text(
        f"✅ <b>تم تعيين الإيموجي المميز</b>\n\n"
        f"الزر: {get_default_label(key)}\n"
        f"الإيموجي ID: <code>{emoji_id}</code>",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 رجوع لتعديل الزر", callback_data=f"bedit_pick_{key}")
        ]]),
        parse_mode="HTML",
    )
    return ConversationHandler.END


# ════════════════════════════════════════════════════════
# إلغاء
# ════════════════════════════════════════════════════════

async def bedit_cancel_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer("تم الإلغاء")
    key = q.data.replace("bedit_cancel_", "")
    await _show_pick(key, update, ctx)          # ← يستخدم المساعد المشترك
    return ConversationHandler.END


async def bedit_cancel_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    key = ctx.user_data.get("bedit_key", "")
    kb  = InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 رجوع لتعديل الزر", callback_data=f"bedit_pick_{key}")
    ]]) if key else None
    await update.message.reply_text("❌ تم الإلغاء.", reply_markup=kb)
    return ConversationHandler.END


# ════════════════════════════════════════════════════════
# تسجيل الـ Handlers
# ════════════════════════════════════════════════════════

admin_btn_colors_handler = CallbackQueryHandler(
    admin_btn_colors_menu, pattern="^admin_btn_colors$"
)
bedit_section_handler = CallbackQueryHandler(
    bedit_section, pattern="^bedit_sec_"
)
bedit_pick_handler = CallbackQueryHandler(
    bedit_pick, pattern="^bedit_pick_"
)
bedit_color_handler = CallbackQueryHandler(
    bedit_color, pattern="^bedit_color_"
)
bedit_delemoji_handler = CallbackQueryHandler(
    bedit_delemoji, pattern="^bedit_delemoji_"
)
bedit_reset_handler = CallbackQueryHandler(
    bedit_reset, pattern="^bedit_reset_"
)

edit_btn_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(bedit_text_start,  pattern="^bedit_text_"),
        CallbackQueryHandler(bedit_emoji_start, pattern="^bedit_emoji_"),
    ],
    states={
        EDIT_BTN_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, bedit_text_receive),
            CallbackQueryHandler(bedit_cancel_cb, pattern="^bedit_cancel_"),
        ],
        EDIT_BTN_EMOJI: [
            MessageHandler(filters.ALL & ~filters.COMMAND, bedit_emoji_receive),
            CallbackQueryHandler(bedit_cancel_cb, pattern="^bedit_cancel_"),
        ],
    },
    fallbacks=[
        MessageHandler(filters.Regex("^/cancel$"), bedit_cancel_cmd),
    ],
    per_message=False,
)
