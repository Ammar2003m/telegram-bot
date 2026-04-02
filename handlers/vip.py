import asyncio
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler, MessageHandler, ConversationHandler, ContextTypes, filters

from config import ADMIN_ID
from db import (
    get_user_vip, vip_progress_text, get_vip_settings, get_active_offers,
    get_all_offers, add_daily_offer, delete_offer, delete_all_offers,
    toggle_offer, set_vip_discount, set_vip_min_spent,
    get_top_spenders, add_user,
)
from keyboards import make_btn as MB, admin_edit_row

SEP = "━━━━━━━━━━━━━━━"

VIP_ICONS = {"normal": "🥉", "mid": "🥈", "vip": "💎"}
VIP_NAMES = {"normal": "عادي", "mid": "مميز ⭐", "vip": "VIP 💎"}

# ── حالات ─────────────────────────────────────────
WAIT_OFFER_TEXT   = 0
WAIT_VIP_DISC     = 10
WAIT_VIP_MIN      = 11


# ════════════════════════════════════════════════════
# عرض حالة VIP للمستخدم
# ════════════════════════════════════════════════════

def _is_visible_name(fn: str) -> bool:
    """يتحقق أن الاسم يحتوي على أحرف مرئية فعلية (لا أحرف Hangul الفارغة أو مسافات فقط)."""
    return bool(fn) and any(
        (ord(c) < 0x3000) or (0xAC00 <= ord(c) <= 0xD7A3)
        for c in fn
    )


async def _top3_text(bot) -> str:
    medals = ["🥇", "🥈", "🥉"]
    rows   = get_top_spenders(3)
    if not rows:
        return ""
    rows = [dict(r) for r in rows if (r["total_spent"] or 0) > 0]
    if not rows:
        return ""
    lines = [f"\n{SEP}\n🏆 توب 3 الأكثر إنفاقاً\n{SEP}"]
    for i, r in enumerate(rows[:3]):
        uid = r["user_id"]
        fn  = (r.get("first_name") or "").strip()

        # إذا لم يكن الاسم مرئياً → اجلبه مباشرةً من Telegram API
        if not _is_visible_name(fn):
            try:
                chat = await bot.get_chat(uid)
                fresh_fn = (chat.first_name or "").strip()
                fresh_un = (chat.username  or "").strip()
                if _is_visible_name(fresh_fn):
                    fn = fresh_fn
                    # حدّث قاعدة البيانات بالاسم الجديد
                    add_user(uid, fresh_un, fresh_fn)
            except Exception:
                pass

        name = fn if _is_visible_name(fn) else "عميل"
        lines.append(f"{medals[i]}  {name}")
    return "\n".join(lines)


async def vip_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    await q.answer()
    uid = q.from_user.id
    total, level, disc = get_user_vip(uid)
    icon  = VIP_ICONS.get(level, "🥉")
    name  = VIP_NAMES.get(level, level)
    prog  = vip_progress_text(uid)
    disc_pct = int(disc * 100)

    text = (
        f"{SEP}\n{icon} مستوى VIP\n{SEP}\n\n"
        f"🏅 مستواك: <b>{name}</b>\n"
        f"💰 إجمالي ما أنفقته: <b>{total:.2f}$</b>\n"
        f"🎁 خصمك الحالي: <b>{disc_pct}%</b>\n\n"
        f"{prog}"
        f"{await _top3_text(ctx.bot)}"
    )
    kb_rows = [
        [MB("🔥 العروض اليومية", "daily_offers", "btn_vip_daily")],
        [MB("⬅️ رجوع",          "main_menu",    "btn_vip_back")],
    ]
    kb_rows += admin_edit_row("vip_sec", uid)
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_rows))


# ════════════════════════════════════════════════════
# العروض اليومية (مستخدم)
# ════════════════════════════════════════════════════

async def daily_offers(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    offers = get_active_offers()
    if not offers:
        text = f"{SEP}\n🔥 العروض اليومية\n{SEP}\n\n❌ لا توجد عروض نشطة حالياً.\nتابعنا لمعرفة أحدث العروض!"
    else:
        lines = [f"{SEP}\n🔥 العروض اليومية\n{SEP}\n"]
        for i, row in enumerate(offers, 1):
            lines.append(f"<b>{i}.</b> {row[1]}")
        text = "\n\n".join(lines)

    kb = InlineKeyboardMarkup([
        [MB("⬅️ رجوع", "vip_status", "btn_offers_back")],
    ])
    await q.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


# ════════════════════════════════════════════════════
# إدارة VIP (أدمن)
# ════════════════════════════════════════════════════

async def admin_vip_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    settings = get_vip_settings()
    lines = [f"{SEP}\n💎 إعدادات VIP\n{SEP}\n"]
    rows  = []
    for s in settings:
        level, min_s, disc = s[0], s[1], s[2]
        icon = VIP_ICONS.get(level, "🏅")
        name = VIP_NAMES.get(level, level)
        lines.append(f"{icon} <b>{name}</b>: من {min_s}$ | خصم {int(disc*100)}%")
        rows.append([
            InlineKeyboardButton(f"خصم {name}", callback_data=f"vip_setdisc_{level}"),
            InlineKeyboardButton(f"حد {name}",  callback_data=f"vip_setmin_{level}"),
        ])

    rows.append([InlineKeyboardButton("🔥 إدارة العروض", callback_data="admin_offers_mgr")])
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel")])

    await q.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows)
    )


# ── تعديل خصم VIP ─────────────────────────────────

async def ask_vip_disc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return
    await q.answer()
    level = q.data.replace("vip_setdisc_", "")
    ctx.user_data["vip_edit"] = {"type": "disc", "level": level}
    name = VIP_NAMES.get(level, level)
    await q.edit_message_text(
        f"أدخل نسبة الخصم لمستوى <b>{name}</b> (مثال: 5 = 5%):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin_vip")]
        ])
    )
    return WAIT_VIP_DISC


async def save_vip_disc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    edit = ctx.user_data.pop("vip_edit", {})
    level = edit.get("level", "")
    try:
        pct = float(update.message.text.strip())
        if not (0 <= pct <= 100):
            raise ValueError
        set_vip_discount(level, pct / 100)
        await update.message.reply_text(f"✅ تم تعديل خصم مستوى {level} إلى {pct:.1f}%")
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً بين 0 و100")
    return ConversationHandler.END


async def ask_vip_min(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return
    await q.answer()
    level = q.data.replace("vip_setmin_", "")
    ctx.user_data["vip_edit"] = {"type": "min", "level": level}
    name = VIP_NAMES.get(level, level)
    await q.edit_message_text(
        f"أدخل الحد الأدنى للإنفاق لمستوى <b>{name}</b> بالدولار:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin_vip")]
        ])
    )
    return WAIT_VIP_MIN


async def save_vip_min(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    edit = ctx.user_data.pop("vip_edit", {})
    level = edit.get("level", "")
    try:
        amount = float(update.message.text.strip())
        if amount < 0:
            raise ValueError
        set_vip_min_spent(level, amount)
        await update.message.reply_text(f"✅ تم تعديل الحد الأدنى لـ {level} إلى {amount}$")
    except ValueError:
        await update.message.reply_text("❌ أدخل رقماً موجباً")
    return ConversationHandler.END


# ════════════════════════════════════════════════════
# إدارة العروض اليومية (أدمن)
# ════════════════════════════════════════════════════

async def admin_offers_panel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    await q.answer()

    offers = get_all_offers()
    rows   = []
    if offers:
        for o in offers:
            oid, text, active = o[0], o[1], o[2]
            status = "✅" if active else "❌"
            short  = text[:30] + "…" if len(text) > 30 else text
            rows.append([
                InlineKeyboardButton(f"{status} {short}", callback_data=f"offer_toggle_{oid}"),
                InlineKeyboardButton("🗑",                  callback_data=f"offer_del_{oid}"),
            ])

    rows.append([InlineKeyboardButton("➕ إضافة عرض",    callback_data="offer_add")])
    rows.append([InlineKeyboardButton("🗑 حذف الكل",      callback_data="offers_delall")])
    rows.append([InlineKeyboardButton("⬅️ رجوع",          callback_data="admin_vip")])

    text = f"{SEP}\n🔥 إدارة العروض اليومية\n{SEP}\n\n"
    text += f"العروض: {len(offers)}" if offers else "لا توجد عروض"

    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))


async def offer_toggle(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    oid = int(q.data.replace("offer_toggle_", ""))
    toggle_offer(oid)
    await q.answer("✅ تم التبديل")
    await admin_offers_panel(update, ctx)


async def offer_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    oid = int(q.data.replace("offer_del_", ""))
    delete_offer(oid)
    await q.answer("🗑 تم الحذف")
    await admin_offers_panel(update, ctx)


async def offers_delete_all(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return await q.answer("🚫", show_alert=True)
    delete_all_offers()
    await q.answer("🗑 تم حذف الكل")
    await admin_offers_panel(update, ctx)


async def ask_offer_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.from_user.id != ADMIN_ID:
        return
    await q.answer()
    await q.edit_message_text(
        "📝 أرسل نص العرض الجديد:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="admin_offers_mgr")]
        ])
    )
    return WAIT_OFFER_TEXT


async def save_offer_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    text = update.message.text.strip()
    if not text:
        await update.message.reply_text("❌ أرسل نصاً صحيحاً")
        return WAIT_OFFER_TEXT
    add_daily_offer(text)
    await update.message.reply_text("✅ تم إضافة العرض!")
    return ConversationHandler.END


# ── ConversationHandlers ───────────────────────────

add_offer_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(ask_offer_text, pattern="^offer_add$")],
    states={
        WAIT_OFFER_TEXT: [
            MessageHandler(filters.TEXT & ~filters.COMMAND, save_offer_text),
        ],
    },
    fallbacks=[CallbackQueryHandler(admin_offers_panel, pattern="^admin_offers_mgr$")],
    per_message=False,
    allow_reentry=True,
)

edit_vip_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(ask_vip_disc, pattern="^vip_setdisc_"),
        CallbackQueryHandler(ask_vip_min,  pattern="^vip_setmin_"),
    ],
    states={
        WAIT_VIP_DISC: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_vip_disc)],
        WAIT_VIP_MIN:  [MessageHandler(filters.TEXT & ~filters.COMMAND, save_vip_min)],
    },
    fallbacks=[CallbackQueryHandler(admin_vip_panel, pattern="^admin_vip$")],
    per_message=False,
    allow_reentry=True,
)

# ── Standalone handlers ────────────────────────────

vip_status_handler      = CallbackQueryHandler(vip_status,          pattern="^vip_status$")
daily_offers_handler    = CallbackQueryHandler(daily_offers,         pattern="^daily_offers$")
admin_vip_handler       = CallbackQueryHandler(admin_vip_panel,      pattern="^admin_vip$")
admin_offers_mgr_handler= CallbackQueryHandler(admin_offers_panel,   pattern="^admin_offers_mgr$")
offer_toggle_handler    = CallbackQueryHandler(offer_toggle,         pattern="^offer_toggle_")
offer_del_handler       = CallbackQueryHandler(offer_delete,         pattern="^offer_del_")
offers_delall_handler   = CallbackQueryHandler(offers_delete_all,    pattern="^offers_delall$")
