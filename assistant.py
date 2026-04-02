"""
الحساب المساعد (Telethon) — يُرسل كود سوا إلى @stc25bot ويقرأ الرد.
نسخة محسّنة: regex ذكي + فحص النجاح + استخراج الرصيد.
"""
import re
import asyncio
import logging

log = logging.getLogger(__name__)

_client = None
_ready  = False
ZBOT = "@stc25bot"
WAIT_REPLY_SEC = 8


def is_ready() -> bool:
    return _ready and _client is not None and _client.is_connected()


async def init_assistant() -> bool:
    global _client, _ready
    from config import API_ID, API_HASH, ASSISTANT_SESSION

    if not all([API_ID, API_HASH, ASSISTANT_SESSION]):
        log.warning("بيانات الحساب المساعد غير مكتملة في config.py — النظام سيعمل يدوياً")
        return False

    try:
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        _client = TelegramClient(StringSession(ASSISTANT_SESSION), API_ID, API_HASH)
        await _client.start()
        me = await _client.get_me()
        log.info(f"الحساب المساعد متصل: {me.first_name} (@{me.username})")
        _ready = True
        return True
    except Exception as e:
        log.error(f"فشل تهيئة الحساب المساعد: {e}")
        _ready = False
        return False


async def send_and_get_response(code: str) -> str | None:
    """يُرسل الكود إلى stc25bot وينتظر الرد الوارد منه فقط (polling)."""
    if not is_ready():
        return None
    try:
        # سجّل وقت الإرسال لنتجاهل الرسائل القديمة
        import time
        sent_at = time.time()

        await _client.send_message(ZBOT, code)
        await asyncio.sleep(WAIT_REPLY_SEC)

        # جلب آخر 5 رسائل وتصفية الواردة فقط من stc25bot (ليست الصادرة منا)
        msgs = await _client.get_messages(ZBOT, limit=5)
        for m in msgs:
            if m.out:          # رسالة صادرة منا — تجاهل
                continue
            if not m.text:     # رسالة بدون نص (صورة/استيكر) — تجاهل
                continue
            if m.date and m.date.timestamp() < sent_at - 2:   # رسالة قديمة قبل إرسالنا
                continue
            log.info(f"stc25bot رد الوارد: {m.text!r}")
            return m.text

        log.warning(f"stc25bot لم يرد على الكود {code!r} خلال {WAIT_REPLY_SEC}ث")
    except Exception as e:
        log.error(f"خطأ في إرسال الكود إلى stc25bot: {e}")
    return None


# ── دوال تحليل الرد ────────────────────────────────────────────────────────

def is_success(text: str) -> bool:
    """يتحقق إن كان الرد يحمل نجاح الشحن."""
    if not text:
        return False
    success_keywords = [
        "تم الشحن بنجاح",
        "تم شحن البطاقة",
        "شحنت بنجاح",
        "تم اضافة",
        "تمت العملية",
        "charged successfully",
    ]
    return any(kw in text for kw in success_keywords)


def extract_amount(text: str) -> float | None:
    """يستخرج قيمة البطاقة بالريال من رد stc25bot."""
    if not text:
        return None
    patterns = [
        r"SAR\s*([\d.]+)",           # SAR 50 أو SAR50
        r"([\d.]+)\s*SAR",           # 50 SAR
        r"([\d.]+)\s*SR",            # 50 SR
        r"المبلغ[:\s]+([\d.]+)",     # المبلغ: 50
        r"القيمة[:\s]+([\d.]+)",     # القيمة: 50
        r"قيمتها[:\s]+([\d.]+)",     # قيمتها 50
        r"([\d.]+)\s*ريال",          # 50 ريال
        r"تم\s+شحن\s+([\d.]+)",      # تم شحن 50
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            val = float(m.group(1))
            if val > 0:
                return val
    return None


def extract_balance(text: str) -> float | None:
    """يستخرج الرصيد المتبقي من رد stc25bot بعد الشحن."""
    if not text:
        return None
    patterns = [
        r"STC\s*([\d.]+)",           # STC 150
        r"الرصيد[:\s]+([\d.]+)",     # الرصيد: 150
        r"رصيدك[:\s]+([\d.]+)",      # رصيدك: 150
        r"رصيد[:\s]+([\d.]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return float(m.group(1))
    return None


def parse_response(text: str) -> dict:
    """
    يُحلّل رد stc25bot ويُعيد dict:
    {
        "success": bool,
        "amount":  float | None,  (بالريال)
        "balance": float | None,  (الرصيد المتبقي)
    }
    """
    success = is_success(text)
    amount  = extract_amount(text)
    balance = extract_balance(text)

    # إذا استُخرج مبلغ حتى بدون كلمة نجاح — نعتبره ناجحاً
    if amount and not success:
        success = True

    return {
        "success": success,
        "amount":  amount,
        "balance": balance,
    }


def get_status_text() -> str:
    """نص حالة الحساب المساعد."""
    if is_ready():
        return "🟢 متصل ويعمل"
    from config import ASSISTANT_SESSION
    if not ASSISTANT_SESSION:
        return "🔴 غير مُعدّ — أضف ASSISTANT_SESSION في config.py"
    return "🟡 معطل — أعد تشغيل البوت"


async def health_check_worker(bot, admin_id: int, interval: int = 300):
    """
    فاحص دوري للحساب المساعد كل `interval` ثانية (افتراضي 5 دقائق).
    يُرسل تنبيهاً للأدمن عند الانقطاع أو العودة.
    """
    import asyncio as _asyncio
    _was_ready = None  # حالة سابقة غير معروفة
    log.info("🩺 بدأ فاحص صحة الحساب المساعد")
    while True:
        await _asyncio.sleep(interval)
        now_ready = is_ready()
        if now_ready != _was_ready:
            if _was_ready is not None:   # تجاهل أول تشغيل
                if not now_ready:
                    msg = (
                        "🔴 <b>تنبيه: الحساب المساعد انقطع!</b>\n\n"
                        "⚠️ شحن السوا التلقائي معطّل.\n"
                        "الطلبات ستُحوَّل يدوياً للأدمن حتى يعود الاتصال."
                    )
                else:
                    msg = "🟢 <b>الحساب المساعد عاد للاتصال.</b>\n✅ شحن السوا التلقائي يعمل الآن."
                try:
                    await bot.send_message(admin_id, msg, parse_mode="HTML")
                except Exception as e:
                    log.error(f"فشل إرسال تنبيه الأدمن: {e}")
            _was_ready = now_ready
