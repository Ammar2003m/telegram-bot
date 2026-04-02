from aiogram import Router, F
from aiogram.types import CallbackQuery

from config import CURRENCY_SYMBOLS
from db import get_user, get_rate, get_user_orders
from keyboards import back_kb, main_menu
from utils import format_balance

router = Router()


@router.callback_query(F.data == "balance")
async def cb_balance(call: CallbackQuery):
    user = await get_user(call.from_user.id)
    if not user:
        return await call.answer("استخدم /start أولاً", show_alert=True)
    currency = user[3] or "USD"
    rate     = await get_rate(currency)
    bal_usd  = user[2]
    bal_fmt  = format_balance(bal_usd, currency, rate)
    await call.message.edit_text(
        f"💰 <b>رصيدك الحالي</b>\n\n"
        f"💵 بالدولار: <b>{bal_usd:.4f} $</b>\n"
        f"💱 بعملتك: <b>{bal_fmt}</b>",
        reply_markup=back_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "orders")
async def cb_my_orders(call: CallbackQuery):
    rows = await get_user_orders(call.from_user.id)
    if not rows:
        await call.message.edit_text(
            "📭 لا يوجد طلبات حتى الآن.",
            reply_markup=back_kb()
        )
    else:
        icons = {"pending": "⏳", "completed": "✅", "done": "✅", "cancelled": "❌"}
        lines = ["🛍 <b>آخر طلباتك:</b>\n"]
        for o in rows:
            icon = icons.get(o[5] if isinstance(o, tuple) else o["status"], "❓")
            oid  = o[0] if isinstance(o, tuple) else o["id"]
            svc  = o[2] if isinstance(o, tuple) else o["service"]
            amt  = o[4] if isinstance(o, tuple) else o["amount"]
            created = o[6] if isinstance(o, tuple) else o["created_at"]
            lines.append(
                f"{icon} <b>#{oid}</b> {svc}\n"
                f"   💲 {amt:.4f}$ | 📅 {str(created)[:10]}"
            )
        await call.message.edit_text(
            "\n".join(lines), reply_markup=back_kb(), parse_mode="HTML"
        )
    await call.answer()


@router.callback_query(F.data == "support")
async def cb_support(call: CallbackQuery):
    await call.message.edit_text(
        "🛠 <b>الدعم الفني</b>\n\nللتواصل مع الدعم أرسل رسالتك وسيتم الرد قريباً.",
        reply_markup=back_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "coupon")
async def cb_coupon(call: CallbackQuery):
    await call.message.edit_text(
        "🎁 <b>كود الخصم</b>\n\nهذه الميزة تُطبّق عند الشراء.\n"
        "أدخل كود الخصم مع طلبك للحصول على تخفيض.",
        reply_markup=back_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "usernames_shop")
async def cb_usernames_shop(call: CallbackQuery):
    from db import get_usernames, convert_from_usd
    rows     = await get_usernames()
    user     = await get_user(call.from_user.id)
    currency = (user[3] if user else None) or "USD"
    sym      = CURRENCY_SYMBOLS.get(currency, currency)

    if not rows:
        await call.message.edit_text(
            "🏷 <b>متجر اليوزرات</b>\n\nلا يوجد يوزرات معروضة حالياً.",
            reply_markup=back_kb(), parse_mode="HTML"
        )
    else:
        lines = ["🏷 <b>اليوزرات المعروضة للبيع:</b>\n"]
        for r in rows:
            price_usd = r[3] if isinstance(r, tuple) else r["price"]
            uname     = r[1] if isinstance(r, tuple) else r["username"]
            rtype     = r[2] if isinstance(r, tuple) else r["type"]
            local     = await convert_from_usd(price_usd, currency)
            lines.append(f"• @{uname} [{rtype}] — {local} {sym}")
        await call.message.edit_text(
            "\n".join(lines) + "\n\nللشراء تواصل مع الدعم.",
            reply_markup=back_kb(), parse_mode="HTML"
        )
    await call.answer()
