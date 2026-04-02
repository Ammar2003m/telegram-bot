"""
طابور معالجة بطاقات سوا — يعمل في الخلفية ويُرسل النتيجة للمستخدم.
"""
import asyncio
import logging
from assistant import send_and_get_response, parse_response, is_ready

log = logging.getLogger(__name__)

sawa_queue: asyncio.Queue = asyncio.Queue()


async def queue_worker(bot):
    """يعمل إلى الأبد، يسحب من الطابور ويعالج بطاقة واحدة في كل مرة."""
    log.info("🔄 بدأ عامل طابور السوا")
    while True:
        uid, code, card_id = await sawa_queue.get()
        try:
            await _process_one(bot, uid, code, card_id)
        except Exception as e:
            log.error(f"خطأ في معالجة البطاقة #{card_id}: {e}")
            try:
                await bot.send_message(
                    uid,
                    "⚠️ حدث خطأ أثناء معالجة بطاقتك، تواصل مع الدعم.",
                )
            except Exception:
                pass
        finally:
            await asyncio.sleep(3)
            sawa_queue.task_done()


async def _send_manual_to_admin(bot, uid: int, code: str, card_id: int, reason: str = ""):
    """
    يُرسل الكرت للأدمن للشحن اليدوي.
    يُنشئ طلباً في قاعدة البيانات ويُعيد (oid) للاستخدام.
    """
    from config import ADMIN_ID
    from db import create_order, get_user
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup

    u        = get_user(uid)
    username = u["username"] if u and u["username"] else None
    name     = f"@{username}" if username else f"<code>{uid}</code>"

    oid = create_order(uid, f"سوا|{code}|يدوي", 0, "pending")

    reason_line = f"\n⚠️ <b>السبب:</b> {reason}" if reason else ""

    await bot.send_message(
        ADMIN_ID,
        f"🔔 <b>كرت سوا يدوي — #{oid}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 المستخدم: {name} (<code>{uid}</code>)\n"
        f"💳 كود البطاقة:\n"
        f"<code>{code}</code>"
        f"{reason_line}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"✅ اضغط <b>شحن يدوي</b> وأدخل قيمة الكرت بالريال\n"
        f"❌ اضغط <b>رفض الكرت</b> إذا كان غير صالح",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ شحن يدوي",  callback_data=f"sawa_d_{oid}_{uid}_{card_id}"),
            InlineKeyboardButton(f"❌ رفض الكرت", callback_data=f"sawa_r_{oid}_{uid}_{card_id}"),
        ]]),
    )
    return oid


async def _process_one(bot, uid: int, code: str, card_id: int):
    from db import (
        update_pending_card, add_card_loaded, add_balance,
        get_card_rate, mark_card_used, create_order,
        add_daily_usage, add_recharge_log,
    )

    # ── حالة 1: الحساب المساعد غير متصل → يدوي فوراً ───────────────────────
    if not is_ready():
        oid = await _send_manual_to_admin(
            bot, uid, code, card_id,
            reason="الحساب المساعد (@stc25bot) غير متصل"
        )
        await bot.send_message(
            uid,
            "⚠️ <b>الشحن التلقائي غير متاح حالياً.</b>\n\n"
            "📨 تم إرسال بطاقتك للمراجعة اليدوية وسيتم شحنها قريباً.\n"
            f"🔖 رقم الطلب: <b>#{oid}</b>",
            parse_mode="HTML",
        )
        return

    # ── حالة 2: إرسال الكود لـ stc25bot وانتظار الرد ──────────────────────────
    await bot.send_message(uid, "🔄 جاري التحقق من البطاقة…")

    raw_text = await send_and_get_response(code)

    log.info(
        f"stc25bot رد [card#{card_id}]: raw={raw_text!r}"
    )

    # ── حالة 2أ: لم يرد stc25bot (timeout/None) → يدوي ───────────────────────
    if raw_text is None:
        oid = await _send_manual_to_admin(
            bot, uid, code, card_id,
            reason="لم يصل رد من @stc25bot (timeout)"
        )
        await bot.send_message(
            uid,
            "⏳ <b>لم يصل رد من نظام الشحن.</b>\n\n"
            "📨 تم تحويل بطاقتك للمراجعة اليدوية وسيتم شحنها قريباً.\n"
            f"🔖 رقم الطلب: <b>#{oid}</b>",
            parse_mode="HTML",
        )
        return

    # ── حالة 2ب: رد stc25bot → تحليل النتيجة ─────────────────────────────────
    result = parse_response(raw_text)

    log.info(
        f"stc25bot [card#{card_id}]: "
        f"success={result['success']} amount={result['amount']}"
    )

    if not result["success"] or not result["amount"]:
        # stc25bot رفض البطاقة → نحوّلها للأدمن للمراجعة اليدوية (لا نرفض تلقائياً)
        oid = await _send_manual_to_admin(
            bot, uid, code, card_id,
            reason=f"stc25bot رفض البطاقة — رد البوت: {raw_text[:120] if raw_text else 'لا يوجد رد'}"
        )
        await bot.send_message(
            uid,
            "⚠️ <b>تعذّرت المعالجة التلقائية.</b>\n\n"
            "📨 تم إرسال بطاقتك للمراجعة اليدوية من الإدارة.\n"
            f"🔖 رقم الطلب: <b>#{oid}</b>\n\n"
            "<i>سيتم الرد عليك في أقرب وقت ممكن.</i>",
            parse_mode="HTML",
        )
        return

    # ── حالة 2ج: نجاح تلقائي ────────────────────────────────────────────────
    amount_sar = result["amount"]
    balance    = result["balance"]

    rate       = get_card_rate("sawa")
    amount_usd = round(amount_sar * rate / 100, 4)

    mark_card_used(code, uid)
    update_pending_card(card_id, "approved", amount_usd)
    add_card_loaded(uid, "sawa", amount_usd)
    add_balance(uid, amount_usd, f"شحن بطاقة سوا {amount_sar:.0f}ر (تلقائي)", "إيداع")
    add_daily_usage(uid, amount_usd)
    create_order(uid, f"شحن سوا {amount_sar:.0f} ريال", amount_usd, "completed")
    add_recharge_log(uid, code, amount_sar, amount_usd, "sawa")

    balance_line = f"📱 رصيد الخط: <b>{balance:.0f} ريال</b>\n" if balance else ""
    await bot.send_message(
        uid,
        f"✅ <b>تم شحن كرت سوا بنجاح!</b>\n\n"
        f"💰 قيمة البطاقة: <b>{amount_sar:.0f} ريال</b>\n"
        f"{balance_line}"
        f"📊 رصيد بطاقتك: <b>+{amount_usd:.2f}$</b>\n\n"
        f"<i>يمكنك طلب السحب من قسم شحن البطاقات.</i>",
        parse_mode="HTML",
    )
