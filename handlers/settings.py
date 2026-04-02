from pdf_gen import generate_statement_pdf
"""
إعدادات المستخدم: الشروط — معلوماتي — تغيير العملة — كشف الحساب
"""
import io
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import CallbackQueryHandler, ContextTypes

from config import ADMIN_ID, CURRENCY_SYMBOLS
from db import (
    get_user, accept_terms, has_accepted_terms,
    get_transactions, convert_from_usd, get_ref_count,
)
from keyboards import main_menu, currency_menu, settings_menu, make_btn as MB
from utils import fmt_bal

log = logging.getLogger(__name__)

SEP  = "━━━━━━━━━━━━━━━━━━━━"
SEP2 = "───────────────────"

TERMS_TEXT = (
    f"{SEP}\n"
    "📜 <b>شروط الاستخدام — متجر روز 🌹</b>\n"
    f"{SEP}\n\n"
    "• جميع العمليات رقمية ولا يمكن التراجع عنها بعد التنفيذ\n"
    "• الرصيد المُودَع غير قابل للسحب النقدي إلا عبر قسم السحب المخصص\n"
    "• يُمنع التلاعب أو استخدام أدوات خارجية أثناء الطلب\n"
    "• التعويض يُطبَّق وفق سياسة المتجر فقط\n"
    "• المتجر غير مسؤول عن أي خسائر ناتجة عن بيانات خاطئة من المستخدم\n"
    "• يحق للإدارة تعليق أي حساب يثير الشبهات\n\n"
    "<i>بالاستمرار فأنت توافق على جميع الشروط أعلاه.</i>"
)

_ORDERS_PER_PAGE = 10


# ── فتح الإعدادات ─────────────────────────────────────────────────────────
async def open_settings(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    await q.edit_message_text("⚙️ <b>إعدادات الحساب</b>", parse_mode="HTML",
                              reply_markup=settings_menu(uid))


# ── عرض الشروط ───────────────────────────────────────────────────────────
async def view_terms(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        TERMS_TEXT,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            MB("⬅️ رجوع", "settings", "btn_settings_back"),
        ]]),
    )


# ── قبول الشروط (يُستدعى من start.py) ──────────────────────────────────
async def accept_terms_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer("✅ تم قبول الشروط!")
    uid  = q.from_user.id
    accept_terms(uid)

    user = get_user(uid)
    if user and user.get("currency"):
        bal = fmt_bal(user["balance"], user["currency"])
        await q.edit_message_text(
            f"✅ <b>تم قبول الشروط بنجاح!</b>\n\n"
            f"أهلاً <b>{q.from_user.first_name}</b> 👋\n"
            f"💰 رصيدك: <b>{bal}</b>",
            parse_mode="HTML",
            reply_markup=main_menu(uid),
        )
    else:
        await q.edit_message_text(
            "✅ <b>تم قبول الشروط!</b>\n\n"
            "مرحباً عزيزي 👋\nاختر عملة حسابك:",
            parse_mode="HTML",
            reply_markup=currency_menu(),
        )


# ── معلوماتي ─────────────────────────────────────────────────────────────
async def my_info_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid  = q.from_user.id
    user = get_user(uid)
    if not user:
        await q.answer("⚠️ استخدم /start أولاً", show_alert=True)
        return

    cur      = user.get("currency") or "USD"
    sym      = CURRENCY_SYMBOLS.get(cur, cur)
    bal_usd  = user.get("balance", 0) or 0
    bal_loc  = convert_from_usd(bal_usd, cur)
    ref_cnt  = get_ref_count(uid)
    vip      = user.get("vip_level") or "عادي"
    uname    = f"@{user['username']}" if user.get("username") else "—"
    name     = user.get("first_name") or q.from_user.first_name or "—"
    total    = user.get("total_spent") or 0

    await q.edit_message_text(
        f"{SEP}\n"
        f"👤 <b>معلومات حسابك</b>\n"
        f"{SEP}\n\n"
        f"🆔 المعرف: <code>{uid}</code>\n"
        f"📛 اليوزر: {uname}\n"
        f"👤 الاسم: <b>{name}</b>\n\n"
        f"💰 الرصيد: <b>{bal_usd:.4f}$</b>  ({bal_loc:.2f} {sym})\n"
        f"📊 الإجمالي المُنفق: <b>{total:.2f}$</b>\n"
        f"🔗 الإحالات: <b>{ref_cnt}</b> مستخدم\n"
        f"💎 مستوى VIP: <b>{vip}</b>\n\n"
        f"{SEP2}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            MB("⬅️ رجوع", "settings", "btn_settings_back"),
        ]]),
    )


# ── كشف الحساب (نصي متعدد الصفحات + PDF اختياري) ─────────────────────
async def my_account_stmt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    await q.edit_message_text("📊 <b>جاري تجهيز كشف الحساب…</b>", parse_mode="HTML")

    user = get_user(uid)
    if not user:
        await q.message.edit_text("⚠️ لم يُعثر على بيانات حسابك.", parse_mode="HTML")
        return

    txs   = [dict(t) for t in get_transactions(uid, limit=200)]
    u     = dict(user)
    pages = _build_user_stmt_pages(uid, u, txs)
    ctx.user_data[f"my_stmt"] = pages

    await q.message.edit_text(
        pages[0],
        parse_mode="HTML",
        reply_markup=_stmt_user_kb(0, len(pages)),
    )

    # ── إرسال PDF للمستخدم ──────────────────────────────────────
    try:
        pdf_bytes = generate_statement_pdf(uid)
        if pdf_bytes:
            with open("stmt.pdf", "wb") as f:
                f.write(pdf_bytes)
            await q.message.reply_document(document=open("stmt.pdf","rb"))
    except Exception as e:
        print("PDF ERROR:", e)
        pdf = generate_statement_pdf(uid)
        if pdf:
            await ctx.bot.send_document(
                uid,
                document=io.BytesIO(pdf),
                filename=f"statement_{uid}.pdf",
                caption="📊 كشف حسابك بصيغة PDF 🌹",
            )
    except Exception as e:
        log.warning(f"فشل إنشاء PDF للمستخدم {uid}: {e}")


async def stmt_page_user_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """تنقل بين صفحات كشف الحساب."""
    q = update.callback_query
    await q.answer()
    page  = int(q.data.split("_")[-1])
    pages = ctx.user_data.get("my_stmt", [])
    if not pages or page >= len(pages):
        await q.answer("⚠️ انتهت الجلسة، افتح الكشف من جديد.", show_alert=True)
        return
    await q.edit_message_text(
        pages[page],
        parse_mode="HTML",
        reply_markup=_stmt_user_kb(page, len(pages)),
    )


def _stmt_user_kb(page: int, total: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(MB("◀️ السابق", f"my_stmt_pg_{page-1}", "btn_prev"))
    if page < total - 1:
        nav.append(MB("التالي ▶️", f"my_stmt_pg_{page+1}", "btn_next"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append([MB("⬅️ رجوع", "settings", "btn_settings_back")])
    return InlineKeyboardMarkup(rows)


_TX_PER_PAGE = 15


def _build_user_stmt_pages(uid: int, u: dict, txs: list) -> list[str]:
    """
    يبني صفحات كشف الحساب من جدول transactions.
    amount > 0 → له (إيداع/عمولة)
    amount < 0 → عليه (خصم/شراء)
    """
    uname   = f"@{u.get('username')}" if u.get("username") else "—"
    name    = (u.get("first_name") or "—").strip() or "—"
    cur     = u.get("currency") or "USD"
    sym     = CURRENCY_SYMBOLS.get(cur, cur)
    bal_usd = u.get("balance", 0) or 0
    bal_loc = convert_from_usd(bal_usd, cur)

    def _loc(usd_val: float) -> str:
        """يُحوّل مبلغ USD للعرض بعملة العميل مع إبقاء الدولار كمرجع."""
        abs_loc = convert_from_usd(abs(usd_val), cur)
        usd_str = f"{abs(usd_val):.4f}$"
        if cur == "USD":
            return usd_str
        if cur == "YER":
            loc_str = f"{abs_loc:,.0f} {sym}"
        else:
            loc_str = f"{abs_loc:,.2f} {sym}"
        return f"{loc_str} (≈ {usd_str})"

    # حساب الإجماليات
    total_in  = sum(t.get("amount", 0) for t in txs if (t.get("amount") or 0) > 0)
    total_out = sum(abs(t.get("amount", 0)) for t in txs if (t.get("amount") or 0) < 0)
    tin_loc   = convert_from_usd(total_in,  cur)
    tout_loc  = convert_from_usd(total_out, cur)
    fmt       = ("{:,.0f}" if cur == "YER" else "{:,.2f}").format

    header = "\n".join([
        SEP,
        "📊 <b>كشف حسابك</b>",
        SEP,
        f"👤 الاسم: <b>{name}</b>",
        f"📛 اليوزر: {uname}",
        f"💰 الرصيد: <b>{bal_loc:.2f} {sym}</b>  (≈ {bal_usd:.4f}$)",
        f"📥 إجمالي الإيداعات: <b>+{fmt(tin_loc)} {sym}</b>",
        f"📤 إجمالي الخصومات: <b>-{fmt(tout_loc)} {sym}</b>",
        f"📋 عدد الحركات: <b>{len(txs)}</b>",
        SEP2,
    ])

    # تقسيم الحركات إلى صفحات
    chunks = [txs[i:i + _TX_PER_PAGE]
              for i in range(0, max(len(txs), 1), _TX_PER_PAGE)]
    if not txs:
        chunks = [[]]

    pages = []
    for ci, chunk in enumerate(chunks):
        parts = [header if ci == 0 else SEP]
        start = ci * _TX_PER_PAGE + 1
        end   = start + len(chunk) - 1

        if txs:
            parts.append(f"\n📋 <b>الحركات ({start}–{end} من {len(txs)}):</b>")
            for t in chunk:
                amt       = t.get("amount") or 0
                note      = str(t.get("note") or t.get("type") or "—")[:35]
                date      = str(t.get("created_at") or "")[:10]
                bal_after = t.get("balance_after") or 0

                amt_display      = _loc(amt)
                bal_after_display = _loc(bal_after)

                if amt > 0:
                    icon      = "🟢"
                    col       = "له"
                    amt_label = f"<b>+{amt_display}</b>"
                else:
                    icon      = "🔴"
                    col       = "عليه"
                    amt_label = f"<b>-{amt_display}</b>"

                parts.append(
                    f"  {icon} {col}: {amt_label}\n"
                    f"     📝 {note}\n"
                    f"     📅 {date}  |  💰 رصيد: {bal_after_display}"
                )
        else:
            parts.append("\n  لا توجد حركات مسجّلة بعد")
            parts.append("  (أي شحن أو شراء سيظهر هنا)")

        pages.append("\n".join(parts))
    return pages


# ── Handlers ─────────────────────────────────────────────────────────────
open_settings_handler    = CallbackQueryHandler(open_settings,    pattern="^settings$")
view_terms_handler       = CallbackQueryHandler(view_terms,       pattern="^view_terms$")
accept_terms_handler     = CallbackQueryHandler(accept_terms_cb,  pattern="^accept_terms$")
my_info_handler          = CallbackQueryHandler(my_info_cb,       pattern="^my_info$")
my_account_stmt_handler  = CallbackQueryHandler(my_account_stmt,  pattern="^my_account_stmt$")
stmt_page_user_handler   = CallbackQueryHandler(stmt_page_user_cb, pattern=r"^my_stmt_pg_\d+$")
