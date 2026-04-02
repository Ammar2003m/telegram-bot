"""
سكريبت تسجيل الدخول إلى Fragment.com وحفظ الجلسة
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
الاستخدام:
    python fragment_login.py

الخطوات:
    1. يفتح متصفح Chrome مرئي
    2. سجّل الدخول وربط محفظة TON
    3. اضغط Enter في الـ terminal
    4. يُحفظ الملف: fragment_session/state.json
    5. ارفع المجلد telegram-bot/fragment_session/ للسيرفر
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

STATE_DIR  = Path(__file__).parent / "fragment_session"
STATE_FILE = STATE_DIR / "state.json"

STATE_DIR.mkdir(exist_ok=True)

print("=" * 55)
print("🔓 Fragment Login — حفظ جلسة تسجيل الدخول")
print("=" * 55)
print()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page    = context.new_page()

    print("🌐 جارٍ فتح Fragment.com ...")
    page.goto("https://fragment.com")

    print()
    print("👆 سجّل الدخول واربط محفظة TON في المتصفح.")
    print("   بعد نجاح الربط اضغط Enter هنا ⬇")
    print()
    input("  [Enter للحفظ] → ")

    context.storage_state(path=str(STATE_FILE))
    browser.close()

print()
print(f"✅ تم الحفظ: {STATE_FILE}")
print(f"   الحجم: {STATE_FILE.stat().st_size} bytes")
print()
print("📤 الآن ارفع مجلد fragment_session/ للسيرفر:")
print("   (في Replit: اسحب المجلد أو استخدم git)")
print("=" * 55)
