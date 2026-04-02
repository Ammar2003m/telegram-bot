"""
طابور معالجة طلبات Fragment (نجوم + بريميوم) — retry + fallback يدوي
"""
import asyncio
import logging
from config import ADMIN_ID as OWNER_ID

log = logging.getLogger(__name__)

MAX_RETRY       = 3
RETRY_DELAY     = 10   # ثانية بين المحاولات
ORDER_DELAY     = 5    # ثانية بين كل طلب وآخر
MANUAL_KB_DATA  = "frag_manual_{oid}"

fragment_queue: asyncio.Queue = asyncio.Queue()


async def fragment_worker(bot):
    """يعمل إلى الأبد — يسحب طلباً من الطابور ويعالجه."""
    log.info("🔄 بدأ عامل طابور Fragment")
    while True:
        order = await fragment_queue.get()
        try:
            await _process_one(bot, order)
        except Exception as e:
            log.error(f"خطأ في معالجة Fragment order #{order.get('oid')}: {e}")
        finally:
            await asyncio.sleep(ORDER_DELAY)
            fragment_queue.task_done()


async def _process_one(bot, order: dict):
    from fragment import send_stars, send_premium, is_fragment_ready
    from db import update_fragment_order

    oid      = order["oid"]
    uid      = order["user_id"]
    svc      = order["svc"]          # "stars" | "premium"
    username = order["username"]
    label    = order["label"]        # "100 ⭐" أو "3 شهور"
    amount   = order.get("amount")   # كمية النجوم (None للبريميوم)
    duration = order.get("duration") # "3"|"6"|"12" (None للنجوم)

    icon = "⭐" if svc == "stars" else "✅"

    # ── إشعار "جاري التنفيذ" ──
    try:
        await bot.send_message(
            uid,
            f"⏳ <b>جاري تنفيذ طلبك تلقائياً...</b>\n"
            f"{icon} {label} → <code>{username}</code>\n"
            f"رقم الطلب: <b>#{oid}</b>",
            parse_mode="HTML",
        )
    except Exception:
        pass

    if not is_fragment_ready():
        log.warning(f"Fragment not ready — طلب #{oid} → تحويل يدوي")
        await _fallback_manual(bot, order, "جلسة Fragment غير مُعدّة")
        update_fragment_order(oid, "manual", "جلسة Fragment غير مُعدّة")
        return

    # ── محاولات التنفيذ ──
    last_error = "فشل غير محدد"
    for attempt in range(1, MAX_RETRY + 1):
        log.info(f"Fragment #{oid} محاولة {attempt}/{MAX_RETRY}")
        try:
            if svc == "stars":
                result = await send_stars(username, int(amount))
            else:
                result = await send_premium(username, str(duration))
        except Exception as e:
            result = {"success": False, "error": str(e)}

        if result["success"]:
            update_fragment_order(oid, "success")
            await _notify_success(bot, uid, icon, label, username, oid)
            await _notify_admin_success(bot, icon, label, username, oid, uid)
            return

        last_error = result.get("error") or "خطأ غير محدد"
        log.warning(f"Fragment #{oid} فشلت محاولة {attempt}: {last_error}")

        if attempt < MAX_RETRY:
            await asyncio.sleep(RETRY_DELAY)

    # ── استنفاد المحاولات → تحويل يدوي ──
    update_fragment_order(oid, "manual", last_error)
    await _fallback_manual(bot, order, last_error)


# ── إشعار نجاح للمستخدم ────────────────────────────────────────────────────

async def _notify_success(bot, uid, icon, label, username, oid):
    try:
        await bot.send_message(
            uid,
            f"✅ <b>تم تنفيذ طلبك بنجاح!</b>\n\n"
            f"{icon} <b>{label}</b>\n"
            f"👤 الحساب: <code>{username}</code>\n"
            f"رقم الطلب: <b>#{oid}</b>",
            parse_mode="HTML",
        )
    except Exception as e:
        log.error(f"send success msg error: {e}")


# ── إشعار نجاح للأدمن ─────────────────────────────────────────────────────

async def _notify_admin_success(bot, icon, label, username, oid, uid):
    try:
        await bot.send_message(
            OWNER_ID,
            f"✅ <b>Fragment نفّذ تلقائياً</b>\n"
            f"{icon} {label} → <code>{username}</code>\n"
            f"المستخدم: <code>{uid}</code> | طلب: #{oid}",
            parse_mode="HTML",
        )
    except Exception:
        pass


# ── تحويل يدوي: إشعار أدمن + مستخدم ───────────────────────────────────────

async def _fallback_manual(bot, order: dict, reason: str):
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    oid      = order["oid"]
    uid      = order["user_id"]
    svc      = order["svc"]
    username = order["username"]
    label    = order["label"]
    icon     = "⭐" if svc == "stars" else "✅"

    kb = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تنفيذ يدوي", callback_data=f"frag_done_{oid}"),
        InlineKeyboardButton("❌ استرداد",    callback_data=f"frag_refund_{oid}"),
    ]])

    try:
        await bot.send_message(
            OWNER_ID,
            f"⚠️ <b>فشل Fragment — يحتاج تنفيذ يدوي</b>\n\n"
            f"{icon} {label}\n"
            f"👤 الحساب: <code>{username}</code>\n"
            f"المستخدم: <code>{uid}</code>\n"
            f"طلب: <b>#{oid}</b>\n"
            f"السبب: {reason}",
            reply_markup=kb,
            parse_mode="HTML",
        )
    except Exception as e:
        log.error(f"notify admin fallback error: {e}")

    try:
        await bot.send_message(
            uid,
            f"⏳ <b>طلبك #{oid} قيد المراجعة اليدوية</b>\n"
            f"سيُنفَّذ خلال 0–12 ساعة. شكراً لصبرك.",
            parse_mode="HTML",
        )
    except Exception:
        pass
