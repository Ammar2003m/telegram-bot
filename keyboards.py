from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import KeyboardButtonStyle
from db import replace_words as rw, get_btn_color, get_btn_label, get_btn_emoji_id
from config import ADMIN_ID

# 1=أخضر  2=أزرق  3=أحمر  0=افتراضي
_STYLE = {
    1: KeyboardButtonStyle.GREEN,
    2: KeyboardButtonStyle.BLUE,
    3: KeyboardButtonStyle.RED,
}


def _btn(default_text: str, cb: str, color_key: str) -> InlineKeyboardButton:
    """ينشئ زر Inline مع لون + نص + إيموجي مميز ديناميكية (Bot API 9.5+)."""
    c        = get_btn_color(color_key)
    style    = _STYLE.get(c)
    label    = get_btn_label(color_key, default_text)
    emoji_id = get_btn_emoji_id(color_key) or None
    return InlineKeyboardButton(
        rw(label),
        callback_data=cb,
        style=style,
        icon_custom_emoji_id=emoji_id,
    )


def _url_btn(default_text: str, url: str, color_key: str) -> InlineKeyboardButton:
    """ينشئ زر URL مع نص + لون + إيموجي قابلة للتعديل."""
    c        = get_btn_color(color_key)
    style    = _STYLE.get(c)
    label    = get_btn_label(color_key, default_text)
    emoji_id = get_btn_emoji_id(color_key) or None
    return InlineKeyboardButton(
        rw(label),
        url=url,
        style=style,
        icon_custom_emoji_id=emoji_id,
    )


def _styled_btn(text: str, cb: str, color_key: str) -> InlineKeyboardButton:
    """لون وإيموجي من قاعدة البيانات — النص دائماً ما يُمرَّر (لا يُستبدل من DB)."""
    c        = get_btn_color(color_key)
    style    = _STYLE.get(c)
    emoji_id = get_btn_emoji_id(color_key) or None
    return InlineKeyboardButton(
        rw(text),
        callback_data=cb,
        style=style,
        icon_custom_emoji_id=emoji_id,
    )


# دوال عامة للاستخدام في جميع الـ handlers
make_btn        = _btn
make_url_btn    = _url_btn
make_styled_btn = _styled_btn


def admin_edit_row(section_key: str, uid: int) -> list:
    """يُعيد قائمة تحتوي صفاً واحداً لزر تعديل الأزرار — فارغة لغير الإدمن."""
    if uid != ADMIN_ID:
        return []
    return [[InlineKeyboardButton(
        "✏️ تعديل أزرار هذه الصفحة",
        callback_data=f"bedit_sec_{section_key}"
    )]]


def currency_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("﷼ يمني",    callback_data="cur_YER"),
         InlineKeyboardButton("﷼ سعودي",   callback_data="cur_SAR")],
        [InlineKeyboardButton("جنيه مصري", callback_data="cur_EGP"),
         InlineKeyboardButton("دولار 🇺🇸",  callback_data="cur_USD")],
    ])


def settings_menu(uid: int = 0) -> InlineKeyboardMarkup:
    rows = [
        [
            _btn("👤 معلوماتي",       "my_info",          "btn_my_info"),
            _btn("🔄 تغيير العملة",   "change_currency",  "btn_change_currency"),
        ],
        [
            _btn("📊 كشف الحساب",    "my_account_stmt",  "btn_my_stmt"),
        ],
        [
            _btn("📜 شروط الاستخدام", "view_terms",       "btn_view_terms"),
        ],
        [
            _btn("⬅️ رجوع",          "back_main",        "btn_settings_back"),
        ],
    ]
    rows += admin_edit_row("settings_sec", uid)
    return InlineKeyboardMarkup(rows)


def main_menu(uid: int = 0) -> InlineKeyboardMarkup:
    from db import is_agent_user
    rows = [
        [
            _btn("💸 نظام الأرباح",  "referral",         "btn_referral"),
        ],
        [
            _btn("الخدمات 🛒",      "services",        "btn_services"),
            _btn("طلباتي 🛍",        "orders",           "btn_orders"),
        ],
        [
            _btn("شحن رصيدي 💳",    "deposit",       "btn_deposit"),
            _btn("شحن بطاقات 💳",   "card_charge",   "btn_card_charge"),
        ],
        [
            _url_btn("قناة البوت 📢", "https://t.me/GGGN9", "btn_channel"),
        ],
        [
            _btn("الدعم 🛠",        "support",          "btn_support"),
            _btn("⚙️ الإعدادات",    "settings",         "btn_settings"),
        ],
        [
            _btn("💎 مستوى VIP",       "vip_status",       "btn_vip"),
            _btn("🔥 العروض اليومية",  "daily_offers",     "btn_offers"),
        ],
        [
            _btn("🤖 المساعد الذكي",  "ai_toggle",        "btn_ai_toggle"),
        ],
        [
            _url_btn("آراء العملاء 💬", "https://t.me/KKGG5/415", "btn_reviews"),
        ],
    ]
    if uid and is_agent_user(uid):
        rows.append([
            InlineKeyboardButton("🧑‍💼 لوحة الوكيل", callback_data="agent_panel"),
        ])
    rows += admin_edit_row("main", uid)
    return InlineKeyboardMarkup(rows)


def admin_panel() -> InlineKeyboardMarkup:
    from db import is_maintenance
    maint_icon = "🟢 تعطيل" if is_maintenance() else "🔴 تفعيل"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💱 العملات",       callback_data="admin_currency"),
            InlineKeyboardButton("👤 المستخدمين",    callback_data="admin_users"),
        ],
        [
            InlineKeyboardButton("📦 الطلبات",       callback_data="admin_orders"),
            InlineKeyboardButton(f"🚧 {maint_icon}", callback_data="admin_maintenance"),
        ],
        [
            InlineKeyboardButton("📢 إذاعة",         callback_data="admin_broadcast"),
            InlineKeyboardButton("🏷 اليوزرات",      callback_data="admin_usernames"),
        ],
        [
            InlineKeyboardButton("💰 شحن يدوي",      callback_data="admin_add_balance"),
            InlineKeyboardButton("🎟 الكوبونات",     callback_data="admin_coupons"),
        ],
        [
            InlineKeyboardButton("💲 الأسعار",        callback_data="admin_prices"),
            InlineKeyboardButton("🎮 أسعار الألعاب", callback_data="admin_games"),
        ],
        [
            InlineKeyboardButton("🔄 استبدال كلمات", callback_data="admin_words"),
            InlineKeyboardButton("✏️ محرر الأزرار",  callback_data="admin_btn_colors"),
        ],
        [
            InlineKeyboardButton("🧑‍💼 إدارة الوكلاء", callback_data="admin_agents"),
            InlineKeyboardButton("💸 تعديل العمولة",   callback_data="admin_ref"),
        ],
        [
            InlineKeyboardButton("💳 إدارة البطاقات",  callback_data="admin_cards"),
            InlineKeyboardButton("⚠️ نقاط الخطورة",   callback_data="admin_risk"),
        ],
        [
            InlineKeyboardButton("💎 نظام VIP",       callback_data="admin_vip"),
            InlineKeyboardButton("🔥 العروض اليومية", callback_data="admin_offers_mgr"),
        ],
        [
            InlineKeyboardButton("📊 كشف حساب عميل", callback_data="admin_cust_stmt"),
            InlineKeyboardButton("💰 رصيد العملاء",   callback_data="admin_balances"),
        ],
        [
            InlineKeyboardButton("🚨 الإنذارات",      callback_data="admin_warnings"),
        ],
        [
            InlineKeyboardButton("🤖 AI المساعد",     callback_data="admin_ai"),
            InlineKeyboardButton("📱 الحساب المساعد", callback_data="admin_assistant"),
        ],
    ])


def back(cb: str = "main_menu") -> InlineKeyboardMarkup:
    from db import get_btn
    label = get_btn("btn_back")
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)]])