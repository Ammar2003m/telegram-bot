"""
أتمتة Fragment.com عبر Playwright
Stars ⭐ و Premium ✅ — جلسة عبر storage_state (state.json)
"""
import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PwTimeout

log = logging.getLogger(__name__)

# ── مسار ملف الجلسة ────────────────────────────────────────────────────────
STATE_FILE     = Path(__file__).parent / "fragment_session" / "state.json"
SCREENSHOT_DIR = Path(__file__).parent / "frag_screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)


# ── حالة الجلسة ─────────────────────────────────────────────────────────────

def is_fragment_ready() -> bool:
    """True إذا كان ملف state.json موجوداً وغير فارغ."""
    return STATE_FILE.exists() and STATE_FILE.stat().st_size > 10


# ── إنشاء المتصفح (headless + storage_state) ────────────────────────────────

async def _launch():
    """يُطلق Chromium headless مع تحميل الجلسة من state.json."""
    pw      = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox"],
    )
    ctx  = await browser.new_context(
        storage_state=str(STATE_FILE),
        viewport={"width": 1280, "height": 800},
    )
    page = await ctx.new_page()
    page.set_default_timeout(30_000)
    return pw, browser, ctx, page


async def _screenshot(page, name: str):
    try:
        path = SCREENSHOT_DIR / f"{name}.png"
        await page.screenshot(path=str(path))
        log.info(f"📸 Screenshot: {path}")
    except Exception:
        pass


async def _close(pw, browser, ctx):
    try:
        await ctx.close()
    except Exception:
        pass
    try:
        await browser.close()
    except Exception:
        pass
    try:
        await pw.stop()
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════════
# إرسال النجوم ⭐
# ══════════════════════════════════════════════════════════════════════════════

async def send_stars(username: str, amount: int) -> dict:
    """
    يرسل نجوم تيليجرام عبر Fragment.com.
    Returns: {'success': bool, 'error': str | None}
    """
    if not is_fragment_ready():
        return {"success": False, "error": "جلسة Fragment غير مُعدّة — ارفع state.json للسيرفر"}

    uname = username.lstrip("@")
    url   = f"https://fragment.com/stars?amount={amount}&recipient={uname}"

    pw = browser = ctx = page = None
    try:
        pw, browser, ctx, page = await _launch()
        log.info(f"⭐ Stars → {uname} × {amount} | URL: {url}")
        await page.goto(url, wait_until="networkidle", timeout=45_000)
        await asyncio.sleep(2)

        # ── التحقق من تسجيل الدخول ──
        content = await page.content()
        if "Connect" in content and "Wallet" in content and "log" not in content.lower():
            await _screenshot(page, f"stars_not_logged_{uname}_{amount}")
            return {"success": False, "error": "الجلسة منتهية — أعد تشغيل fragment_login.py"}

        # ── حقل المستخدم ──
        user_field = None
        for sel in [
            'input[placeholder*="username"]',
            'input[placeholder*="Username"]',
            'input[name="recipient"]',
            'input[name="username"]',
            'input[autocomplete="off"]',
        ]:
            try:
                user_field = page.locator(sel).first
                await user_field.wait_for(timeout=3_000)
                break
            except Exception:
                user_field = None

        if user_field:
            await user_field.fill(uname)
            await asyncio.sleep(1)

        # ── حقل الكمية ──
        amount_field = None
        for sel in [
            'input[type="number"]',
            'input[name="amount"]',
            'input[placeholder*="amount"]',
            'input[placeholder*="Amount"]',
        ]:
            try:
                amount_field = page.locator(sel).first
                await amount_field.wait_for(timeout=3_000)
                break
            except Exception:
                amount_field = None

        if amount_field:
            await amount_field.fill(str(amount))
            await asyncio.sleep(1)

        # ── زر الشراء ──
        clicked = False
        for sel in [
            "text=Buy", "text=Continue", "text=Send", "text=شراء",
            'button[type="submit"]', ".tm-button-primary",
        ]:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(timeout=3_000)
                await btn.click()
                clicked = True
                break
            except Exception:
                pass

        if not clicked:
            await _screenshot(page, f"stars_no_btn_{uname}_{amount}")
            return {"success": False, "error": "لم يُعثر على زر الشراء في Fragment"}

        await asyncio.sleep(5)
        content = await page.content()

        success_hints = ["success", "sent", "تم", "Stars sent", "Transaction"]
        if any(h.lower() in content.lower() for h in success_hints):
            log.info(f"✅ Stars sent: {uname} × {amount}")
            return {"success": True, "error": None}

        error_hints = ["error", "failed", "خطأ", "فشل", "insufficient"]
        if any(h.lower() in content.lower() for h in error_hints):
            await _screenshot(page, f"stars_error_{uname}_{amount}")
            return {"success": False, "error": "فشل التنفيذ في Fragment (خطأ في الصفحة)"}

        await _screenshot(page, f"stars_unknown_{uname}_{amount}")
        return {"success": False, "error": "نتيجة غير معروفة — راجع السكرين شوت"}

    except PwTimeout:
        if page:
            await _screenshot(page, f"stars_timeout_{uname}_{amount}")
        return {"success": False, "error": "انتهت مدة الانتظار (timeout) في Fragment"}

    except Exception as e:
        log.exception(f"خطأ في send_stars: {e}")
        if page:
            await _screenshot(page, f"stars_exc_{uname}_{amount}")
        return {"success": False, "error": f"خطأ: {e}"}

    finally:
        if pw:
            await _close(pw, browser, ctx)


# ══════════════════════════════════════════════════════════════════════════════
# هدية البريميوم ✅
# ══════════════════════════════════════════════════════════════════════════════

_DURATION_TEXT = {"3": "3 months", "6": "6 months", "12": "1 year"}


async def send_premium(username: str, duration: str) -> dict:
    """
    يرسل هدية Telegram Premium عبر Fragment.com.
    duration: '3' | '6' | '12' (شهور)
    Returns: {'success': bool, 'error': str | None}
    """
    if not is_fragment_ready():
        return {"success": False, "error": "جلسة Fragment غير مُعدّة — ارفع state.json للسيرفر"}

    uname    = username.lstrip("@")
    dur_text = _DURATION_TEXT.get(duration, "3 months")
    url      = "https://fragment.com/premium"

    pw = browser = ctx = page = None
    try:
        pw, browser, ctx, page = await _launch()
        log.info(f"✅ Premium → {uname} × {duration}m | URL: {url}")
        await page.goto(url, wait_until="networkidle", timeout=45_000)
        await asyncio.sleep(2)

        # ── التحقق من تسجيل الدخول ──
        content = await page.content()
        if "Connect" in content and "Wallet" in content and "log" not in content.lower():
            await _screenshot(page, f"prem_not_logged_{uname}_{duration}")
            return {"success": False, "error": "الجلسة منتهية — أعد تشغيل fragment_login.py"}

        # ── حقل المستخدم ──
        user_field = None
        for sel in [
            'input[placeholder*="username"]',
            'input[placeholder*="Username"]',
            'input[name="recipient"]',
            'input[name="username"]',
        ]:
            try:
                user_field = page.locator(sel).first
                await user_field.wait_for(timeout=3_000)
                break
            except Exception:
                user_field = None

        if user_field:
            await user_field.fill(uname)
            await asyncio.sleep(1)

        # ── اختيار المدة ──
        for sel in [
            f"text={dur_text}",
            f"text={duration} month",
            f'[data-duration="{duration}"]',
            f'input[value="{duration}"]',
        ]:
            try:
                dur_el = page.locator(sel).first
                await dur_el.wait_for(timeout=3_000)
                await dur_el.click()
                break
            except Exception:
                pass

        await asyncio.sleep(1)

        # ── زر Gift / Buy ──
        clicked = False
        for sel in [
            "text=Gift", "text=Buy", "text=Send", "text=Continue",
            'button[type="submit"]', ".tm-button-primary",
        ]:
            try:
                btn = page.locator(sel).first
                await btn.wait_for(timeout=3_000)
                await btn.click()
                clicked = True
                break
            except Exception:
                pass

        if not clicked:
            await _screenshot(page, f"prem_no_btn_{uname}_{duration}")
            return {"success": False, "error": "لم يُعثر على زر Gift في Fragment"}

        await asyncio.sleep(5)
        content = await page.content()

        success_hints = ["success", "sent", "تم", "Premium sent", "Transaction", "gift"]
        if any(h.lower() in content.lower() for h in success_hints):
            log.info(f"✅ Premium sent: {uname} × {duration}m")
            return {"success": True, "error": None}

        error_hints = ["error", "failed", "خطأ", "فشل", "insufficient"]
        if any(h.lower() in content.lower() for h in error_hints):
            await _screenshot(page, f"prem_error_{uname}_{duration}")
            return {"success": False, "error": "فشل التنفيذ في Fragment (خطأ في الصفحة)"}

        await _screenshot(page, f"prem_unknown_{uname}_{duration}")
        return {"success": False, "error": "نتيجة غير معروفة — راجع السكرين شوت"}

    except PwTimeout:
        if page:
            await _screenshot(page, f"prem_timeout_{uname}_{duration}")
        return {"success": False, "error": "انتهت مدة الانتظار (timeout) في Fragment"}

    except Exception as e:
        log.exception(f"خطأ في send_premium: {e}")
        if page:
            await _screenshot(page, f"prem_exc_{uname}_{duration}")
        return {"success": False, "error": f"خطأ: {e}"}

    finally:
        if pw:
            await _close(pw, browser, ctx)
