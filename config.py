import os

# ══════════════════════════════════════════════════
# إعدادات البوت — @StoreRozbot
# على VPS: ضع store.db بجانب main.py مباشرة
# ══════════════════════════════════════════════════

BOT_TOKEN = os.getenv("BOT_TOKEN", "7390710856:AAEs1JRtczszPfzacbLt0nkGDHTSK6luWuc")
ADMIN_ID  = int(os.getenv("OWNER_ID", "671524794"))

# قاعدة البيانات — في نفس مجلد البوت
DB_PATH = "store.db"
DB = DB_PATH

# ── بيانات الحساب المساعد (Telethon) ──────────────
API_ID   = 37482697
API_HASH = "641532e51333885415eba80837e32193"
ASSISTANT_SESSION = "1BJWap1sAUJkBIvQyXzUX4kZGYlb7hQH2Gcmtlatyg1mRSRW8xRY0roEtX-bb9FE_F2WZexJHoByWELIurAnddP6IdrX0-Nk05bkhq_wVfF4jI4gDXROPsmkhiiDYQ9iVyfJAZPxg4tonAmwMnr8C_tG0MCFEipv0KcE6gGnz5konzHHnGQnlIsTfvUOLH_SpLrBrlg6cra8T5Zi-pJujRTSj5zXgKcFZcW-ST7yYbEtUhVyCYezX0euPYKZZUHjSAfM0gom_J6RcNgmxYiIGBvFn4pj8hDc8pBR1Lr7kQi6pqk95FiTan2RQGpXCCT_7wh3tJhMBw-5BRLSHFh11oX3yRYXmJQ0="

# ── إعدادات عامة ──────────────────────────────────
DEFAULT_RATES = {
    "USD":  1,
    "YER":  550,
    "SAR":  3.75,
    "EGP":  50,
    "USDT": 1,
}

CURRENCY_SYMBOLS = {
    "USD":  "$",
    "SAR":  "﷼",
    "YER":  "﷼",
    "EGP":  "ج.م",
    "USDT": "$",
}

CURRENCY_NAMES = {
    "USD":  "دولار 🇺🇸",
    "SAR":  "ريال سعودي 🇸🇦",
    "YER":  "ريال يمني 🇾🇪",
    "EGP":  "جنيه مصري 🇪🇬",
    "USDT": "USDT",
}

WALLET_USDT = os.getenv("WALLET_USDT_TRC20", "—")

# ── CryptoPay API ──────────────────────────────────
CRYPTO_API_TOKEN = os.getenv("CRYPTO_API_TOKEN", "557847:AAYhe04WsJFf8vgQDZIwVtDUK8LJ9iS0dBz")

# ── TG-Lion API ────────────────────────────────────
TG_API_KEY = os.getenv("TG_API_KEY", "hgm84x15fcazwi93ey")
TG_API_URL = os.getenv("TG_API_URL", "https://www.tg-lion.net/api")
TG_MARGIN  = float(os.getenv("TG_MARGIN", "0.3"))

PREMIUM_PRICES = {"3m": (13, "3 أشهر"), "6m": (18, "6 أشهر"), "12m": (31, "سنة")}
STARS_QTYS    = [50, 100, 200, 500, 750, 1000, 2000, 3000]
FAKE_USD      = 2.0
NETFLIX_PLANS = {
    "basic":    ("الأساسية",  "720p",      1),
    "standard": ("القياسية",  "1080p",     2),
    "premium":  ("المميزة",   "4K + HDR",  4),
}
PRICES = {
    "pubg_mobile": {
        "10": 0.37, "60": 1.03, "120": 2.21, "180": 3.21,
        "325": 4.67, "385": 5.68, "660": 9.29, "720": 10.20,
        "985": 15.18, "1320": 20.32, "1800": 23.48, "2125": 31.12,
    },
    "pubg_new_state": {
        "300": 1.21, "1580": 5.61, "3580": 13.08, "10230": 34.58,
    },
    "free_fire": {
        "583": 5.61, "1188": 11.21, "2420": 23.36, "6160": 56.07,
    },
    "cod": {
        "420": 5.61, "880": 11.21, "2400": 24.30, "5000": 50.47,
    },
}
