import re
import sqlite3
import threading
import time
from config import DB, DEFAULT_RATES


# ══════════════════════════════════════════════════
# Cache خفيف للبيانات ثابتة (أزرار / كلمات / أسعار)
# ══════════════════════════════════════════════════
_CACHE: dict = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL  = 30.0   # ثانية


def _cache_get(ns: str):
    with _CACHE_LOCK:
        entry = _CACHE.get(ns)
        if entry and time.monotonic() < entry[1]:
            return entry[0]
    return None


def _cache_set(ns: str, value, ttl: float = _CACHE_TTL):
    with _CACHE_LOCK:
        _CACHE[ns] = (value, time.monotonic() + ttl)


def cache_clear(ns: str | None = None):
    """امسح الكاش كله أو بالاسم."""
    with _CACHE_LOCK:
        if ns is None:
            _CACHE.clear()
        else:
            _CACHE.pop(ns, None)


def connect() -> sqlite3.Connection:
    import os
    if not os.path.exists(DB):
        raise FileNotFoundError(
            f"\n\n❌ قاعدة البيانات غير موجودة: {DB}\n"
            f"   انسخ store.db من السيرفر القديم إلى مجلد البوت\n"
        )
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id      INTEGER PRIMARY KEY,
            username     TEXT    DEFAULT '',
            balance      REAL    DEFAULT 0,
            currency     TEXT    DEFAULT 'USD',
            is_banned    INTEGER DEFAULT 0,
            sawa_loaded  REAL    DEFAULT 0,
            like_loaded  REAL    DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value REAL
        );

        CREATE TABLE IF NOT EXISTS orders (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            service    TEXT,
            details    TEXT,
            amount     REAL,
            status     TEXT    DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS coupons (
            code        TEXT PRIMARY KEY,
            discount    REAL,
            is_active   INTEGER DEFAULT 1,
            usage_limit INTEGER DEFAULT 1,
            used_count  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS usernames (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            username        TEXT,
            type            TEXT,
            price           REAL,
            status          TEXT DEFAULT 'available',
            reserved_by     INTEGER DEFAULT NULL,
            reserved_until  REAL    DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS prices (
            service TEXT PRIMARY KEY,
            price   REAL
        );

        CREATE TABLE IF NOT EXISTS ui_texts (
            key  TEXT PRIMARY KEY,
            text TEXT
        );

        CREATE TABLE IF NOT EXISTS words (
            old TEXT PRIMARY KEY,
            new TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS button_colors (
            key      TEXT PRIMARY KEY,
            color    INTEGER DEFAULT 0,
            label    TEXT    DEFAULT '',
            emoji_id TEXT    DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS reply_buttons (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            text      TEXT NOT NULL,
            text_html TEXT NOT NULL,
            color     TEXT DEFAULT 'blue',
            url       TEXT DEFAULT '',
            emoji_id  TEXT DEFAULT '',
            position  INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS support (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            message    TEXT,
            reply      TEXT,
            status     TEXT    DEFAULT 'open',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS str_settings (
            key   TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS services (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            category  TEXT    NOT NULL,
            name      TEXT    NOT NULL,
            value     TEXT    NOT NULL,
            price_usd REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agent_prices (
            service TEXT PRIMARY KEY,
            price   REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS referrals (
            user_id     INTEGER PRIMARY KEY,
            referrer_id INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS processed_invoices (
            invoice_id   TEXT PRIMARY KEY,
            processed_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ai_memory (
            user_id    INTEGER PRIMARY KEY,
            history    TEXT    DEFAULT '[]',
            updated_at TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS ai_suspicious (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            message    TEXT,
            logged_at  TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS review_dismissed (
            user_id    INTEGER PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            type          TEXT    NOT NULL DEFAULT 'إيداع',
            amount        REAL    NOT NULL,
            balance_after REAL    NOT NULL DEFAULT 0,
            note          TEXT    DEFAULT '',
            created_at    TEXT    DEFAULT (datetime('now'))
        );
        """)

        # ── Migration: إعادة بناء جدول services إن كان ناقصاً ──
        _svc_cols = [r[1] for r in db.execute("PRAGMA table_info(services)").fetchall()]
        if _svc_cols and "category" not in _svc_cols:
            db.execute("DROP TABLE services")
            db.execute("""
            CREATE TABLE services (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                category  TEXT    NOT NULL,
                name      TEXT    NOT NULL,
                value     TEXT    NOT NULL,
                price_usd REAL    NOT NULL
            )
            """)

        # ── Migrations (safe, idempotent) ─────────────────────
        for col, defval in [("label", "''"), ("emoji_id", "''")]:
            try:
                db.execute(
                    f"ALTER TABLE button_colors ADD COLUMN {col} TEXT DEFAULT {defval}"
                )
                db.commit()
            except Exception:
                pass

        # Migration: عمود is_agent في جدول users
        try:
            db.execute("ALTER TABLE users ADD COLUMN is_agent INTEGER DEFAULT 0")
            db.commit()
        except Exception:
            pass

        # Migration: عمود warnings في جدول users
        try:
            db.execute("ALTER TABLE users ADD COLUMN warnings INTEGER DEFAULT 0")
            db.commit()
        except Exception:
            pass

        # Migration: عمود first_name في جدول users
        try:
            db.execute("ALTER TABLE users ADD COLUMN first_name TEXT DEFAULT ''")
            db.commit()
        except Exception:
            pass

        # Migration: عمود accepted_terms
        try:
            db.execute("ALTER TABLE users ADD COLUMN accepted_terms INTEGER DEFAULT 0")
            db.commit()
        except Exception:
            pass

        # Migration: عمود total_spent
        try:
            db.execute("ALTER TABLE users ADD COLUMN total_spent REAL DEFAULT 0")
            db.commit()
        except Exception:
            pass

        for k, v in DEFAULT_RATES.items():
            db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))

        default_prices = {
            "stars_100":    1.80,
            "stars_1000":   1.65,
            "stars_per_usd": round(100 / 1.3, 4),   # 100 نجمة = 1.3$
            "like_1000":    0.10,
            "view_1":       0.03,
            "view_10":      0.05,
            "view_20":      0.08,
            "view_30":      0.10,
            "boost_10":     2.50,
            "member_90":    2.00,
            "member_180":   4.00,
            "member_365":   5.00,
            "transfer_1000": 8.00,
            "net_basic":    5.00,
            "net_standard": 10.00,
            "net_premium":  15.00,
            "prem_3m":      13.00,
            "prem_6m":      18.00,
            "prem_12m":     31.00,
            "rush_price":        2.00,
            "rush_premium_1k":   7.50,
        }
        for k, v in default_prices.items():
            db.execute("INSERT OR IGNORE INTO prices(service,price) VALUES(?,?)", (k, v))

        default_texts = {
            "welcome":            "أهلاً بك في متجر روز 🌹\nاختر من القائمة:",
            "main_menu":          "القائمة الرئيسية 🌹",
            "services_menu":      "🛒 قائمة الخدمات",
            "telegram_services":  "🟦 خدمات تيليجرامية",
            "general_menu":       "🌐 الخدمات العامة",
        }
        for k, v in default_texts.items():
            db.execute("INSERT OR IGNORE INTO ui_texts(key,text) VALUES(?,?)", (k, v))

        db.commit()


# ── المستخدمون ──────────────────────────────────

def add_user(user_id: int, username: str, first_name: str = ""):
    with connect() as db:
        # currency=NULL مقصودة → يُجبر المستخدم الجديد على اختيار عملته
        db.execute(
            "INSERT OR IGNORE INTO users(user_id,username,first_name,currency)"
            " VALUES(?,?,?,NULL)",
            (user_id, username or "", first_name or "")
        )
        db.execute(
            "UPDATE users SET username=?, first_name=? WHERE user_id=?",
            (username or "", first_name or "", user_id)
        )
        db.commit()


def get_user(user_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def set_currency(user_id: int, currency: str):
    with connect() as db:
        db.execute("UPDATE users SET currency=? WHERE user_id=?", (currency, user_id))
        db.commit()


def get_balance(user_id: int) -> float:
    row = get_user(user_id)
    return row["balance"] if row else 0.0


def add_balance(user_id: int, amount: float, note: str = "", tx_type: str = "إيداع"):
    """يُضيف رصيداً ويُسجّل العملية في جدول transactions تلقائياً."""
    with connect() as db:
        db.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (amount, user_id))
        db.commit()
        row = db.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()
        bal_after = row[0] if row else 0.0
        db.execute(
            "INSERT INTO transactions(user_id,type,amount,balance_after,note) VALUES(?,?,?,?,?)",
            (user_id, tx_type, amount, bal_after, note or "إيداع رصيد")
        )
        db.commit()
    print(f"TRANSACTION: uid={user_id} type={tx_type} amount=+{amount:.4f} bal_after={bal_after:.4f} note={note!r}")


def remove_balance(user_id: int, amount: float, note: str = "", tx_type: str = "خصم"):
    """خصم آمن — يمنع السالب ويوقف التلاعب"""
    with connect() as db:
        row = db.execute(
            "SELECT balance FROM users WHERE user_id=?",
            (user_id,)
        ).fetchone()

        if not row:
            return False

        current_balance = row[0] or 0.0

        # ❌ منع السحب إذا الرصيد غير كافي
        if current_balance < amount:
            return False

        # ✅ تنفيذ الخصم
        new_balance = current_balance - amount

        db.execute(
            "UPDATE users SET balance=?, total_spent=total_spent+? WHERE user_id=?",
            (new_balance, amount, user_id)
        )
        db.commit()

        db.execute(
            "INSERT INTO transactions(user_id,type,amount,balance_after,note) VALUES(?,?,?,?,?)",
            (user_id, tx_type, -amount, new_balance, note or "خصم رصيد")
        )
        db.commit()

    print(f"[SAFE REMOVE] uid={user_id} -{amount} => {new_balance}")
    return True


def update_balance(user_id: int, amount: float, note: str = ""):
    """(wrapper) → add_balance — للتوافق مع الكود القديم."""
    add_balance(user_id, amount, note or "تحديث رصيد", "إيداع")


def deduct_balance(user_id: int, amount: float, note: str = ""):
    """(wrapper) → remove_balance — للتوافق مع الكود القديم."""
    remove_balance(user_id, amount, note or "خصم رصيد", "خصم")


def is_banned(user_id: int) -> bool:
    row = get_user(user_id)
    return bool(row["is_banned"]) if row else False


def toggle_ban(user_id: int, status: int):
    with connect() as db:
        db.execute("UPDATE users SET is_banned=? WHERE user_id=?", (status, user_id))
        db.commit()


def get_all_user_ids() -> list[int]:
    with connect() as db:
        return [r[0] for r in db.execute("SELECT user_id FROM users").fetchall()]


# ── نظام الوكلاء ──────────────────────────────────

def is_agent_user(user_id: int) -> bool:
    with connect() as db:
        row = db.execute("SELECT is_agent FROM users WHERE user_id=?", (user_id,)).fetchone()
        return bool(row["is_agent"]) if row else False


def set_agent_status(user_id: int, status: int):
    with connect() as db:
        if status == 1:
            db.execute(
                "UPDATE users SET is_agent=1, currency='USD' WHERE user_id=?",
                (user_id,)
            )
        else:
            db.execute("UPDATE users SET is_agent=0 WHERE user_id=?", (user_id,))
        db.commit()


def get_agent_effective_price(service: str) -> float:
    """يعيد سعر الوكيل الخاص إن وُجد، وإلا يعيد السعر العادي."""
    ag = get_agent_price(service)
    if ag is not None:
        return ag
    return get_price(service)


def get_agents() -> list:
    with connect() as db:
        return db.execute(
            "SELECT user_id, username, balance FROM users WHERE is_agent=1"
        ).fetchall()


def get_agent_price(service: str) -> float | None:
    with connect() as db:
        row = db.execute(
            "SELECT price FROM agent_prices WHERE service=?", (service,)
        ).fetchone()
        return row["price"] if row else None


def set_agent_price(service: str, price: float):
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO agent_prices(service,price) VALUES(?,?)",
            (service, price)
        )
        db.commit()


def get_all_agent_prices() -> list:
    with connect() as db:
        rows = db.execute("SELECT service, price FROM agent_prices ORDER BY service").fetchall()
        return [dict(r) for r in rows]


def delete_agent_price(service: str):
    with connect() as db:
        db.execute("DELETE FROM agent_prices WHERE service=?", (service,))
        db.commit()


# ── نظام الإحالات ──────────────────────────────────

def add_referral(user_id: int, referrer_id: int):
    """يسجّل إحالة (يتجاهل إن كانت موجودة مسبقاً)."""
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO referrals(user_id, referrer_id) VALUES(?,?)",
            (user_id, referrer_id)
        )
        db.commit()


def get_referrer(user_id: int):
    """يُرجع ID الشخص الذي أحال هذا المستخدم أو None."""
    with connect() as db:
        row = db.execute(
            "SELECT referrer_id FROM referrals WHERE user_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else None


def get_ref_count(user_id: int) -> int:
    """عدد المستخدمين الذين أحالهم هذا المستخدم."""
    with connect() as db:
        row = db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)
        ).fetchone()
        return row[0] if row else 0


def get_ref_percent() -> float:
    """نسبة العمولة الحالية (%)."""
    return float(get_str_setting("ref_percent", "10"))


def set_ref_percent(value: float):
    """تغيير نسبة العمولة."""
    set_str_setting("ref_percent", str(value))


# ── فواتير CryptoPay ──────────────────────────────

def is_invoice_processed(invoice_id) -> bool:
    """هل تمت معالجة هذه الفاتورة مسبقاً؟"""
    with connect() as db:
        r = db.execute(
            "SELECT 1 FROM processed_invoices WHERE invoice_id=?",
            (str(invoice_id),)
        ).fetchone()
        return r is not None


def mark_invoice_processed(invoice_id):
    """تسجيل الفاتورة كمُعالَجة."""
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO processed_invoices (invoice_id) VALUES (?)",
            (str(invoice_id),)
        )


# ── أسعار الصرف ─────────────────────────────────

def get_rate(currency: str) -> float:
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (currency,)).fetchone()
        return row[0] if row else 1.0


def update_rate(currency: str, value: float):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (currency, value))
        db.commit()


def get_all_rates() -> dict:
    with connect() as db:
        return {r[0]: r[1] for r in db.execute("SELECT key,value FROM settings").fetchall()}


def convert_from_usd(amount: float, currency: str) -> float:
    return round(amount * get_rate(currency), 2)


def convert_to_usd(amount: float, currency: str) -> float:
    rate = get_rate(currency)
    return round(amount / rate, 4) if rate else 0.0


# ── الطلبات ─────────────────────────────────────

def create_order(user_id: int, service: str, details: str, amount: float) -> int:
    with connect() as db:
        cur = db.execute(
            "INSERT INTO orders(user_id,service,details,amount) VALUES(?,?,?,?)",
            (user_id, service, details, amount)
        )
        db.commit()
        return cur.lastrowid


def get_order(order_id: int):
    with connect() as db:
        row = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None


def update_order_status(order_id: int, status: str):
    with connect() as db:
        db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
        db.commit()


def get_user_orders(user_id: int) -> list:
    with connect() as db:
        return db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (user_id,)
        ).fetchall()


def accept_terms(uid: int):
    """يُسجّل قبول الشروط للمستخدم."""
    with connect() as db:
        db.execute("UPDATE users SET accepted_terms=1 WHERE user_id=?", (uid,))
        db.commit()


def has_accepted_terms(uid: int) -> bool:
    """هل وافق المستخدم على الشروط؟"""
    with connect() as db:
        row = db.execute(
            "SELECT accepted_terms FROM users WHERE user_id=?", (uid,)
        ).fetchone()
        return bool(row and row[0])


def get_users_balances_page(offset: int = 0, limit: int = 10) -> list:
    """يُرجع صفحة من المستخدمين مرتبة تنازلياً حسب الرصيد."""
    with connect() as db:
        rows = db.execute(
            "SELECT user_id, first_name, username, balance FROM users "
            "ORDER BY balance DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


def count_total_users() -> int:
    """إجمالي عدد المستخدمين."""
    with connect() as db:
        row = db.execute("SELECT COUNT(*) FROM users").fetchone()
        return row[0] if row else 0


def get_user_statement(uid: int) -> dict:
    """كشف حساب شامل: جميع الطلبات + شحن البطاقات + السحوبات."""
    with connect() as db:
        user = db.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        orders = db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()
        cards = db.execute(
            "SELECT * FROM pending_cards WHERE user_id=? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()
        withdrawals = db.execute(
            "SELECT * FROM withdrawals WHERE user_id=? ORDER BY created_at DESC",
            (uid,)
        ).fetchall()
        ref_count = db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,)
        ).fetchone()[0]
    return {
        "user":        user,
        "orders":      orders,
        "cards":       cards,
        "withdrawals": withdrawals,
        "ref_count":   ref_count,
    }


def get_transactions(uid: int, limit: int = 100) -> list:
    """يُعيد قائمة الحركات المالية للمستخدم من جدول transactions."""
    with connect() as db:
        return db.execute(
            "SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (uid, limit)
        ).fetchall()


# ── الكوبونات ────────────────────────────────────

def add_coupon(code: str, discount: float, usage_limit: int):
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO coupons(code,discount,usage_limit) VALUES(?,?,?)",
            (code, discount, usage_limit)
        )
        db.commit()


def get_coupons() -> list:
    with connect() as db:
        return db.execute("SELECT * FROM coupons").fetchall()


def delete_coupon(code: str):
    with connect() as db:
        db.execute("DELETE FROM coupons WHERE code=?", (code,))
        db.commit()


# ── اليوزرات ─────────────────────────────────────

def _migrate_usernames():
    """يضيف الأعمدة الجديدة لجدول usernames إذا لم تكن موجودة."""
    with connect() as db:
        cols = {r[1] for r in db.execute("PRAGMA table_info(usernames)")}
        if "status" not in cols:
            db.execute("ALTER TABLE usernames ADD COLUMN status TEXT DEFAULT 'available'")
        if "reserved_by" not in cols:
            db.execute("ALTER TABLE usernames ADD COLUMN reserved_by INTEGER DEFAULT NULL")
        if "reserved_until" not in cols:
            db.execute("ALTER TABLE usernames ADD COLUMN reserved_until REAL DEFAULT NULL")
        db.commit()


def add_username_db(username: str, type_: str, price: float):
    with connect() as db:
        db.execute(
            "INSERT INTO usernames(username,type,price,status) VALUES(?,?,?,'available')",
            (username, type_, price)
        )
        db.commit()


def get_usernames() -> list:
    """جميع اليوزرات (للأدمن)."""
    with connect() as db:
        return db.execute("SELECT * FROM usernames ORDER BY status, id").fetchall()


def get_available_usernames() -> list:
    """اليوزرات المتاحة فقط (للعملاء) — ينظّف المحجوزات المنتهية أولاً."""
    import time
    with connect() as db:
        # فك حجز المنتهية
        db.execute(
            "UPDATE usernames SET status='available', reserved_by=NULL, reserved_until=NULL "
            "WHERE status='reserved' AND reserved_until < ?",
            (time.time(),)
        )
        db.commit()
        return db.execute(
            "SELECT * FROM usernames WHERE status='available' ORDER BY price"
        ).fetchall()


def reserve_username(row_id: int, uid: int, seconds: int = 90) -> bool:
    """يحجز اليوزر مؤقتاً. يُرجع True إذا نجح."""
    import time
    with connect() as db:
        cur = db.execute(
            "UPDATE usernames SET status='reserved', reserved_by=?, reserved_until=? "
            "WHERE id=? AND status='available'",
            (uid, time.time() + seconds, row_id)
        )
        db.commit()
        return cur.rowcount > 0


def release_username(row_id: int):
    """يفك حجز اليوزر ويُعيده للمتاح."""
    with connect() as db:
        db.execute(
            "UPDATE usernames SET status='available', reserved_by=NULL, reserved_until=NULL "
            "WHERE id=?", (row_id,)
        )
        db.commit()


def mark_username_sold(row_id: int):
    """يضع اليوزر كمباع."""
    with connect() as db:
        db.execute(
            "UPDATE usernames SET status='sold', reserved_by=NULL, reserved_until=NULL "
            "WHERE id=?", (row_id,)
        )
        db.commit()


def get_username_by_id(row_id: int):
    with connect() as db:
        return db.execute("SELECT * FROM usernames WHERE id=?", (row_id,)).fetchone()


def delete_username_db(uid: int):
    with connect() as db:
        db.execute("DELETE FROM usernames WHERE id=?", (uid,))
        db.commit()


# ── أسعار الخدمات ────────────────────────────────

def _load_prices() -> dict:
    cached = _cache_get("prices")
    if cached is not None:
        return cached
    with connect() as db:
        data = {r[0]: r[1] for r in db.execute("SELECT service,price FROM prices").fetchall()}
    _cache_set("prices", data, ttl=60.0)
    return data


def get_price(service: str) -> float:
    return _load_prices().get(service, 0.0)


def update_price(service: str, new_price: float):
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO prices(service,price) VALUES(?,?)", (service, new_price))
        db.commit()
    cache_clear("prices")


def get_all_prices() -> dict:
    return dict(sorted(_load_prices().items()))


# ── الدعم الفني ──────────────────────────────────

def create_ticket(user_id: int, message: str) -> int:
    with connect() as db:
        cur = db.execute(
            "INSERT INTO support(user_id, message) VALUES(?,?)",
            (user_id, message)
        )
        db.commit()
        return cur.lastrowid


def save_reply(ticket_id: int, reply: str) -> int:
    """يحفظ رد الأدمن دون إغلاق التذكرة — الإغلاق يتم عبر close_ticket فقط."""
    with connect() as db:
        db.execute(
            "UPDATE support SET reply=? WHERE id=?",
            (reply, ticket_id)
        )
        db.commit()
        row = db.execute("SELECT user_id FROM support WHERE id=?", (ticket_id,)).fetchone()
        return row[0] if row else None


def get_user_tickets(user_id: int, limit: int = 5):
    with connect() as db:
        return db.execute(
            "SELECT id, message, reply, status, created_at FROM support "
            "WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()


def get_ticket(ticket_id: int):
    with connect() as db:
        return db.execute(
            "SELECT * FROM support WHERE id=?", (ticket_id,)
        ).fetchone()


def close_ticket(ticket_id: int):
    with connect() as db:
        db.execute(
            "UPDATE support SET status='closed' WHERE id=?",
            (ticket_id,)
        )
        db.commit()


# ── الإنذارات ────────────────────────────────────

def get_warnings(user_id: int) -> int:
    with connect() as db:
        row = db.execute(
            "SELECT warnings FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return row["warnings"] if row else 0


def warn_user(user_id: int) -> tuple[int, bool]:
    """يضيف إنذاراً. يعيد (عدد_الإنذارات, تم_الحظر)."""
    with connect() as db:
        db.execute(
            "UPDATE users SET warnings = warnings + 1 WHERE user_id=?",
            (user_id,)
        )
        db.commit()
        row = db.execute(
            "SELECT warnings FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        count = row["warnings"] if row else 1
        banned = False
        if count >= 3:
            db.execute(
                "UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,)
            )
            db.commit()
            banned = True
        return count, banned


def reset_warnings(user_id: int):
    with connect() as db:
        db.execute(
            "UPDATE users SET warnings=0 WHERE user_id=?", (user_id,)
        )
        db.commit()


# ── نصوص الواجهة الديناميكية ─────────────────────

def get_text(key: str, fallback: str = "") -> str:
    """جلب نص واجهة من قاعدة البيانات مع تطبيق استبدال الكلمات (HTML).
    استخدم مع parse_mode='HTML' لعرض الإيموجي المميز."""
    with connect() as db:
        row = db.execute("SELECT text FROM ui_texts WHERE key=?", (key,)).fetchone()
    raw = row["text"] if row else (fallback or f"[{key}]")
    return replace_words_html(raw)


def update_text(key: str, new_text: str):
    """تحديث أو إنشاء نص واجهة."""
    with connect() as db:
        db.execute(
            "INSERT INTO ui_texts(key,text) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET text=excluded.text",
            (key, new_text)
        )
        db.commit()


def get_all_texts() -> list:
    """جلب كل النصوص القابلة للتعديل."""
    with connect() as db:
        return db.execute("SELECT key, text FROM ui_texts ORDER BY key").fetchall()


# ── ألوان أزرار القائمة الرئيسية ────────────────────

# 0=افتراضي  1=أخضر  2=أزرق  3=أحمر
BTN_COLOR_MAP   = {"default": 0, "green": 1, "blue": 2, "red": 3}
BTN_COLOR_NAMES = {0: "⬜ افتراضي", 1: "🟩 أخضر", 2: "🟦 أزرق", 3: "🟥 أحمر"}

# ── أقسام الأزرار ─────────────────────────────────────
BUTTON_SECTIONS = {
    "main":         "🏠 القائمة الرئيسية",
    "services":     "🛒 قائمة الخدمات",
    "tg":           "🟦 خدمات تيليجرام",
    "gsm_nav":      "⭐ قوائم خدمات تيليجرام",
    "general":      "🌐 الخدمات العامة",
    "games":        "🎮 قسم الألعاب",
    "deposit":      "💳 قائمة الإيداع",
    "cards":        "🃏 قائمة شحن البطاقات",
    "orders_sec":   "📋 قائمة الطلبات",
    "usernames_sec":"🆔 متجر اليوزرات",
    "stc_sec":      "📶 باقات STC",
    "direct_pay":   "🛒 شراء الآن (رصيد غير كافٍ)",
    "support_sec":  "🛟 قائمة الدعم الفني",
    "vip_sec":      "💎 قائمة VIP والعروض",
    "nav":          "⬅️ أزرار التنقل",
    "links":        "🔗 روابط سريعة",
    "review":       "⭐ نافذة تقييم الخدمة",
    "settings_sec": "⚙️ قائمة الإعدادات",
}

# key → (section, default_label)
ALL_BTNS = {
    # ── القائمة الرئيسية ──
    "btn_referral":      ("main",     "💸 نظام الأرباح"),
    "btn_services":      ("main",     "الخدمات 🛒"),
    "btn_orders":        ("main",     "طلباتي 🛍"),
    "btn_deposit":       ("main",     "شحن رصيدي 💳"),
    "btn_coupon":        ("main",     "كود خصم 🎁"),
    "btn_support":       ("main",     "الدعم 🛠"),
    "btn_currency":      ("main",     "تغيير العملة 🔄"),
    "btn_ai_toggle":     ("main",     "🤖 المساعد الذكي"),
    # ── قائمة الخدمات ──
    "btn_svc_telegram":  ("services", "خدمات تيليجرامية 🟦"),
    "btn_svc_general":   ("services", "خدمات عامة 🌐"),
    "btn_svc_insta":     ("services", "انستجرام 📸 (قريباً)"),
    # ── خدمات تيليجرام ──
    "btn_tg_premium":    ("tg",       "تيليجرام المميز ✅"),
    "btn_tg_stars":      ("tg",       "النجوم ⭐️"),
    "btn_tg_rush":       ("tg",       "الرشق 🚀"),
    "btn_tg_transfer":   ("tg",       "نقل أعضاء 🔄"),
    "btn_tg_boosts":     ("tg",       "تعزيزات ⚡️"),
    "btn_tg_usernames":  ("tg",       "يوزرات 🆔"),
    "btn_tg_numbers":          ("tg",       "شراء رقم 📲"),
    "btn_tg_collectibles":     ("tg",       "💎 مقتنيات رقمية"),
    "btn_rush_premium_members":("gsm_nav",  "رشق أعضاء مميزين 🌟"),
    # ── الخدمات العامة ──
    "btn_gen_netflix":   ("general",  "نتفلكس 🍿"),
    "btn_gen_crypto":    ("general",  "عملات رقمية 💲"),
    "btn_gen_games":     ("general",  "شحن ألعاب 🎮"),
    # ── قسم الألعاب ──
    "btn_game_pubg":     ("games",    "PUBG Mobile 🔫"),
    "btn_game_newstate": ("games",    "PUBG New State 🆕"),
    "btn_game_freefire": ("games",    "Free Fire 💎"),
    # ── قائمة الإيداع — الدول ──
    "btn_dep_yemen":     ("deposit",  "🇾🇪 اليمن"),
    "btn_dep_saudi":     ("deposit",  "🇸🇦 السعودية"),
    "btn_dep_egypt":     ("deposit",  "🇪🇬 مصر"),
    "btn_dep_crypto":    ("deposit",  "💲 عملات رقمية"),
    # ── قائمة الإيداع — مبلغ مخصص ──
    "btn_dep_custom":    ("deposit",  "✏️ مبلغ مخصص"),
    # ── طرق دفع اليمن ──
    "btn_dep_kurimi":    ("deposit",  "🏦 بنك الكريمي"),
    "btn_dep_jeeb":      ("deposit",  "📱 محفظة جيب"),
    "btn_dep_onecash":   ("deposit",  "💚 ون كاش"),
    "btn_dep_floosak":   ("deposit",  "📲 جوالي / فلوسك"),
    "btn_dep_nametrans": ("deposit",  "🔄 تحويل بالاسم"),
    # ── طرق دفع السعودية ──
    "btn_dep_alarabi":   ("deposit",  "🏦 بنك العربي"),
    "btn_dep_alinma":    ("deposit",  "🏦 بنك الإنماء"),
    # ── طرق دفع مصر ──
    "btn_dep_vodafone":  ("deposit",  "📱 فودافون كاش"),
    # ── طرق دفع كريبتو ──
    "btn_dep_binance":   ("deposit",  "🟡 Binance ID"),
    "btn_dep_cryptopay": ("deposit",  "🤖 CryptoPay (تلقائي)"),
    # ── الخدمات العامة (إضافية) ──
    "btn_gen_stc":       ("general",  "باقات سوا STC 📶"),
    "btn_gen_cards":     ("general",  "شحن بطاقات 💳"),
    # ── القائمة الرئيسية (إضافية) ──
    "btn_card_charge":   ("main",     "شحن بطاقات 💳"),
    "btn_vip":           ("main",     "💎 مستوى VIP"),
    "btn_offers":        ("main",     "🔥 العروض اليومية"),
    # ── قائمة شحن البطاقات ──
    "btn_card_sawa":      ("cards",        "📶 شحن سوا"),
    "btn_card_like":      ("cards",        "💳 شحن لايك كارد"),
    "btn_card_withdraw":  ("cards",        "💸 سحب رصيد البطاقات"),
    "btn_card_history":   ("cards",        "📋 سجل الشحن"),
    # ── قائمة الإيداع (إضافية) ──
    "btn_dep_stars":      ("deposit",      "⭐ نجوم تيليجرام"),
    "btn_dep_stars_custom":("deposit",     "🔢 كمية مخصصة"),
    # ── قوائم خدمات تيليجرام ──
    "btn_rush_members":   ("gsm_nav",      "رشق أعضاء 👥"),
    "btn_rush_likes":     ("gsm_nav",      "رشق تفاعلات 👍"),
    "btn_rush_views":     ("gsm_nav",      "رشق مشاهدات 👁"),
    "btn_stars_custom_qty":("gsm_nav",     "✏️ كمية مخصصة"),
    # ── الخدمات العامة — نتفلكس ──
    "btn_net_own_email":  ("general",      "✉️ إيميلي الخاص"),
    "btn_net_new_email":  ("general",      "📧 إيميل جديد"),
    # ── قائمة الطلبات ──
    "btn_orders_reorder": ("orders_sec",   "🔁 إعادة آخر طلب"),
    "btn_orders_popular": ("orders_sec",   "🔥 الأكثر طلباً"),
    # ── متجر اليوزرات ──
    "btn_uname_confirm":  ("usernames_sec","✅ تأكيد الشراء"),
    # ── باقات STC ──
    "btn_stc_confirm":    ("stc_sec",      "✅ تأكيد"),
    "btn_stc_back":       ("stc_sec",      "🔙 رجوع لقائمة STC"),
    # ── شراء الآن (رصيد غير كافٍ) ──
    "btn_buy_now":        ("direct_pay",   "🛒 شراء الآن"),
    # ── قائمة الدعم الفني ──
    "btn_sup_tickets":    ("support_sec",  "📩 تذاكري"),
    "btn_sup_new":        ("support_sec",  "✏️ تذكرة جديدة"),
    "btn_sup_human":      ("support_sec",  "👤 الدعم البشري"),
    "btn_sup_back_main":  ("support_sec",  "🔙 القائمة الرئيسية"),
    "btn_sup_cancel":     ("support_sec",  "❌ إلغاء"),
    "btn_sup_back":       ("support_sec",  "🔙 رجوع"),
    "btn_sup_tix_back":   ("support_sec",  "🔙 رجوع للتذاكر"),
    # ── قائمة شحن البطاقات (تنقل) ──
    "btn_cards_back":     ("cards",        "🔙 رجوع"),
    # ── قسم الألعاب (تنقل) ──
    "btn_games_back":     ("games",        "🔙 رجوع"),
    "btn_games_pkg_back": ("games",        "🔙 رجوع"),
    # ── قائمة VIP والعروض ──
    "btn_vip_daily":      ("vip_sec",      "🔥 العروض اليومية"),
    "btn_vip_back":       ("vip_sec",      "⬅️ رجوع"),
    "btn_offers_back":    ("vip_sec",      "⬅️ رجوع"),
    # ── أزرار التنقل العامة ──
    "btn_back":           ("nav",          "⬅️ رجوع"),
    "btn_back_main":      ("nav",          "⬅️ القائمة الرئيسية"),
    "btn_confirm":        ("nav",          "تأكيد ✅"),
    "btn_cancel":         ("nav",          "إلغاء ❌"),
    "btn_charge":         ("nav",          "💳 شحن رصيدي"),
    "btn_pay_direct":     ("nav",          "💰 الدفع المباشر"),
    "btn_support_nav":    ("nav",          "🛟 الدعم"),
    # ── روابط سريعة (URL) ──
    "btn_channel":        ("links",        "قناة البوت 📢"),
    "btn_admin_contact":  ("links",        "تواصل معنا 👤"),
    # ── آراء العملاء — القائمة الرئيسية ──
    "btn_reviews":        ("main",         "آراء العملاء 💬"),
    # ── أزرار التقييم (تظهر بعد اكتمال الطلبات) ──
    "btn_review_rate":    ("review",       "✍️ قيّمنا هنا"),
    "btn_review_dismiss": ("review",       "🔕 لا تذكرني"),
    # ── قائمة الإعدادات ──
    "btn_settings":       ("settings_sec", "⚙️ الإعدادات"),
    "btn_my_info":        ("settings_sec", "👤 معلوماتي"),
    "btn_my_stmt":        ("settings_sec", "📊 كشف الحساب"),
    "btn_view_terms":     ("settings_sec", "📜 شروط الاستخدام"),
    "btn_accept_terms":   ("settings_sec", "✅ أوافق على الشروط"),
    "btn_change_currency":("settings_sec", "🔄 تغيير العملة"),
    "btn_settings_back":  ("settings_sec", "⬅️ رجوع"),
    # ── أزرار التصفح (التالي / السابق) ──
    "btn_next":           ("nav",          "التالي ▶️"),
    "btn_prev":           ("nav",          "◀️ السابق"),
}

# backward compat
MAIN_MENU_BTNS = {k: v[1] for k, v in ALL_BTNS.items() if v[0] == "main"}


def get_default_label(key: str) -> str:
    return ALL_BTNS[key][1] if key in ALL_BTNS else key


def _load_btn_settings() -> dict:
    """قراءة جميع إعدادات الأزرار دفعة واحدة مع cache."""
    cached = _cache_get("btn_settings")
    if cached is not None:
        return cached
    with connect() as db:
        rows = db.execute("SELECT key,color,label,emoji_id FROM button_colors").fetchall()
        data = {
            r["key"]: {
                "color":    r["color"],
                "label":    r["label"] or "",
                "emoji_id": r["emoji_id"] or "",
            }
            for r in rows
        }
    _cache_set("btn_settings", data)
    return data


def _invalidate_btn_cache():
    cache_clear("btn_settings")


def get_btn(key: str) -> str:
    """يعيد نص الزر المخصص (أو النص الافتراضي) — بدون لون."""
    lbl = _load_btn_settings().get(key, {}).get("label", "")
    return lbl if lbl else get_default_label(key)


def get_btn_color(key: str) -> int:
    return _load_btn_settings().get(key, {}).get("color", 0)


def set_btn_color(key: str, color: int):
    with connect() as db:
        db.execute(
            "INSERT INTO button_colors(key,color) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET color=excluded.color",
            (key, color)
        )
        db.commit()
    _invalidate_btn_cache()


def get_btn_label(key: str, default: str = "") -> str:
    """يعيد النص المخصص للزر، أو default إذا لم يُعيَّن."""
    lbl = _load_btn_settings().get(key, {}).get("label", "")
    return lbl if lbl else default


def set_btn_label(key: str, label: str):
    with connect() as db:
        db.execute(
            "INSERT INTO button_colors(key,color,label,emoji_id) VALUES(?,0,?,'')"
            " ON CONFLICT(key) DO UPDATE SET label=excluded.label",
            (key, label)
        )
        db.commit()
    _invalidate_btn_cache()


def get_btn_emoji_id(key: str) -> str:
    """يعيد معرّف الإيموجي المميز للزر (فارغ إذا لم يُعيَّن)."""
    return _load_btn_settings().get(key, {}).get("emoji_id", "")


def set_btn_emoji_id(key: str, emoji_id: str):
    with connect() as db:
        db.execute(
            "INSERT INTO button_colors(key,color,label,emoji_id) VALUES(?,0,'',?)"
            " ON CONFLICT(key) DO UPDATE SET emoji_id=excluded.emoji_id",
            (key, emoji_id)
        )
        db.commit()
    _invalidate_btn_cache()


def get_all_btn_settings() -> dict:
    """يعيد dict: key → {color, label, emoji_id}"""
    return dict(_load_btn_settings())


# ── أزرار الكيبورد الديناميكية ───────────────────────

def add_reply_button(text: str, text_html: str, color: str, url: str = "", emoji_id: str = ""):
    with connect() as db:
        pos = db.execute("SELECT COALESCE(MAX(position),0)+1 FROM reply_buttons").fetchone()[0]
        db.execute(
            "INSERT INTO reply_buttons(text,text_html,color,url,emoji_id,position) VALUES(?,?,?,?,?,?)",
            (text, text_html, color, url or "", emoji_id or "", pos)
        )
        db.commit()


def get_reply_buttons() -> list:
    with connect() as db:
        return db.execute(
            "SELECT id,text,text_html,color,url,emoji_id FROM reply_buttons ORDER BY position,id"
        ).fetchall()


def delete_reply_button(bid: int):
    with connect() as db:
        db.execute("DELETE FROM reply_buttons WHERE id=?", (bid,))
        db.commit()


def build_inline_keyboard():
    """يبني InlineKeyboardMarkup من الأزرار المخصصة. يعيد None إذا لا يوجد أزرار."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows_data = get_reply_buttons()
    if not rows_data:
        return None
    COLOR_PREFIX = {"blue": "🟦", "green": "🟩", "red": "🟥"}
    keyboard = []
    row = []
    for i, btn in enumerate(rows_data, 1):
        prefix = COLOR_PREFIX.get(btn["color"], "")
        label  = f"{prefix} {btn['text']}".strip() if prefix else btn["text"]
        url    = btn["url"] or ""
        if url:
            kb_btn = InlineKeyboardButton(label, url=url)
        else:
            kb_btn = InlineKeyboardButton(label, callback_data=f"custombtn_{btn['id']}")
        row.append(kb_btn)
        if i % 2 == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)


# ── استبدال الكلمات العالمي ─────────────────────────

def _strip_html(text: str) -> str:
    """احذف وسوم HTML مع الإبقاء على محتواها (الإيموجي الاحتياطي)."""
    return re.sub(r"<[^>]+>", "", text)


def _load_words() -> list[tuple[str, str]]:
    """قراءة جميع الكلمات من DB مع cache — قائمة (old, new_html)."""
    cached = _cache_get("words")
    if cached is not None:
        return cached
    with connect() as db:
        data = [(r["old"], r["new"]) for r in db.execute("SELECT old, new FROM words").fetchall()]
    _cache_set("words", data, ttl=60.0)
    return data


def replace_words(text: str) -> str:
    """استبدال الكلمات — نسخة نص عادي (للأزرار وغير HTML)."""
    if not text:
        return text
    for old, new_html in _load_words():
        text = text.replace(old, _strip_html(new_html))
    return text


def replace_words_html(text: str) -> str:
    """استبدال الكلمات — نسخة HTML (يحتفظ بـ <tg-emoji>)."""
    if not text:
        return text
    for old, new_html in _load_words():
        text = text.replace(old, new_html)
    return text


def add_word(old: str, new_html: str):
    """يخزّن الكلمة الجديدة كـ HTML (يشمل <tg-emoji> للإيموجي المميز)."""
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO words(old,new) VALUES(?,?)", (old, new_html))
        db.commit()
    cache_clear("words")


def get_all_words() -> list:
    with connect() as db:
        return db.execute("SELECT old, new FROM words ORDER BY old").fetchall()


def delete_word(old: str):
    with connect() as db:
        db.execute("DELETE FROM words WHERE old=?", (old,))
        db.commit()
    cache_clear("words")


def search_words(query: str) -> list:
    with connect() as db:
        return db.execute(
            "SELECT old, new FROM words WHERE old LIKE ? OR new LIKE ?",
            (f"%{query}%", f"%{query}%")
        ).fetchall()


# ── الإحصائيات ───────────────────────────────────

def get_stats() -> tuple[int, int]:
    with connect() as db:
        users  = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        return users, orders


def get_rich_stats() -> dict:
    """إحصائيات موسّعة للأدمن."""
    with connect() as db:
        users    = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        orders   = db.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        pending  = db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0]
        done     = db.execute("SELECT COUNT(*) FROM orders WHERE status IN ('completed','done')").fetchone()[0]
        cancelled= db.execute("SELECT COUNT(*) FROM orders WHERE status='cancelled'").fetchone()[0]
        revenue  = db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status IN ('completed','done')"
        ).fetchone()[0]
        today    = db.execute(
            "SELECT COUNT(*) FROM orders WHERE DATE(created_at)=DATE('now')"
        ).fetchone()[0]
        today_rev= db.execute(
            "SELECT COALESCE(SUM(amount),0) FROM orders "
            "WHERE DATE(created_at)=DATE('now') AND status IN ('completed','done')"
        ).fetchone()[0]
        return {
            "users": users, "orders": orders, "pending": pending,
            "done": done, "cancelled": cancelled,
            "revenue": revenue, "today": today, "today_rev": today_rev,
        }


# ── أعلى المنفقين ─────────────────────────────────

def get_top_spenders(limit: int = 3) -> list:
    """يعيد أعلى المنفقين محسوبًا من جدول الطلبات المكتملة."""
    with connect() as db:
        return db.execute(
            """
            SELECT u.user_id, u.username, u.first_name,
                   COALESCE(SUM(o.amount), 0) AS total_spent
            FROM users u
            LEFT JOIN orders o
                ON o.user_id = u.user_id
               AND o.status IN ('completed', 'done', 'approved')
            GROUP BY u.user_id
            ORDER BY total_spent DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()


def backfill_total_spent():
    """يحدّث عمود total_spent لكل مستخدم من مجموع طلباته المكتملة (تُستدعى عند بدء التشغيل)."""
    with connect() as db:
        rows = db.execute(
            """
            SELECT user_id, COALESCE(SUM(amount), 0) AS real_spent
            FROM orders
            WHERE status IN ('completed', 'done', 'approved')
            GROUP BY user_id
            """
        ).fetchall()
        for r in rows:
            uid, spent = r[0], r[1]
            level = get_vip_level_for(spent)
            db.execute(
                "UPDATE users SET total_spent=?, vip_level=? WHERE user_id=?",
                (spent, level, uid)
            )
        db.commit()


# ── تقييمات الخدمة (dismiss) ───────────────────────

def is_review_dismissed(user_id: int) -> bool:
    with connect() as db:
        r = db.execute(
            "SELECT 1 FROM review_dismissed WHERE user_id=?", (user_id,)
        ).fetchone()
        return r is not None


def dismiss_review(user_id: int):
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO review_dismissed(user_id) VALUES(?)", (user_id,)
        )


# ── الأكثر طلباً ─────────────────────────────────

def get_popular_services(limit: int = 5) -> list:
    with connect() as db:
        return db.execute(
            "SELECT service, COUNT(*) as total FROM orders "
            "GROUP BY service ORDER BY total DESC LIMIT ?",
            (limit,)
        ).fetchall()


# ── آخر طلب للمستخدم ─────────────────────────────

def get_last_order(user_id: int):
    with connect() as db:
        return db.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,)
        ).fetchone()


# ── الإعدادات النصية (صيانة، إلخ) ───────────────

def get_str_setting(key: str, default: str = "") -> str:
    with connect() as db:
        row = db.execute(
            "SELECT value FROM str_settings WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else default


def set_str_setting(key: str, value: str):
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO str_settings(key,value) VALUES(?,?)",
            (key, value)
        )
        db.commit()


def is_maintenance() -> bool:
    return get_str_setting("maintenance", "off") == "on"


# ── خدمات الألعاب (services table) ───────────────

def get_services(category: str) -> list:
    with connect() as db:
        return db.execute(
            "SELECT id, name, value, price_usd FROM services WHERE category=? ORDER BY price_usd",
            (category,)
        ).fetchall()


def get_service_by_id(sid: int):
    with connect() as db:
        return db.execute(
            "SELECT id, category, name, value, price_usd FROM services WHERE id=?",
            (sid,)
        ).fetchone()


def update_service_price(sid: int, price_usd: float):
    with connect() as db:
        db.execute("UPDATE services SET price_usd=? WHERE id=?", (price_usd, sid))
        db.commit()


def seed_game_services():
    """يُدرج بيانات الألعاب الأولية مرة واحدة فقط."""
    GAMES_DATA = {
        "pubg": [
            ("10 UC",   "10",   0.37),
            ("60 UC",   "60",   1.03),
            ("120 UC",  "120",  2.21),
            ("180 UC",  "180",  3.21),
            ("325 UC",  "325",  4.67),
            ("385 UC",  "385",  5.68),
            ("660 UC",  "660",  9.29),
            ("720 UC",  "720",  10.20),
            ("985 UC",  "985",  15.18),
            ("1320 UC", "1320", 20.32),
            ("1800 UC", "1800", 23.48),
            ("2125 UC", "2125", 31.12),
        ],
        "newstate": [
            ("300 NC",   "300",   1.21),
            ("1580 NC",  "1580",  5.61),
            ("3580 NC",  "3580",  13.08),
            ("10230 NC", "10230", 34.58),
        ],
        "freefire": [
            ("530+53 ماسة",    "530+53",    5.61),
            ("1080+108 ماسة",  "1080+108",  11.21),
            ("2200+220 ماسة",  "2200+220",  23.36),
            ("5600+560 ماسة",  "5600+560",  56.07),
        ],
    }
    with connect() as db:
        for cat, rows in GAMES_DATA.items():
            exists = db.execute(
                "SELECT COUNT(*) FROM services WHERE category=?", (cat,)
            ).fetchone()[0]
            if exists:
                continue
            for name, value, price in rows:
                db.execute(
                    "INSERT INTO services(category,name,value,price_usd) VALUES(?,?,?,?)",
                    (cat, name, value, price)
                )
        db.commit()

# ════════════════════════════════════════════════════
# ── جداول ومهاجرات جديدة: البطاقات + الحماية + STC ─
# ════════════════════════════════════════════════════

def _migrate_cards():
    """ينشئ الجداول الجديدة إن لم تكن موجودة (idempotent)."""
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS used_cards (
            code       TEXT PRIMARY KEY,
            user_id    INTEGER,
            used_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS pending_cards (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            card_type  TEXT,
            code       TEXT,
            status     TEXT DEFAULT 'pending',
            amount     REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS card_daily (
            user_id    INTEGER,
            date_str   TEXT,
            amount     REAL DEFAULT 0,
            PRIMARY KEY (user_id, date_str)
        );

        CREATE TABLE IF NOT EXISTS risk_scores (
            user_id    INTEGER PRIMARY KEY,
            score      INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        db.executescript("""
        CREATE TABLE IF NOT EXISTS withdrawals (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            country    TEXT,
            method     TEXT,
            info       TEXT,
            status     TEXT DEFAULT 'pending',
            amount_usd REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS recharge_log (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER,
            code       TEXT,
            amount_sar REAL,
            amount_usd REAL,
            service    TEXT DEFAULT 'sawa',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)
        # إضافة معدلات البطاقات الافتراضية في settings
        for k, v in [("rate_sawa", 23.0), ("rate_like", 23.0)]:
            db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
        # إضافة أعمدة sawa_loaded و like_loaded للمستخدمين القديمين
        try:
            db.execute("ALTER TABLE users ADD COLUMN sawa_loaded REAL DEFAULT 0")
        except Exception:
            pass
        try:
            db.execute("ALTER TABLE users ADD COLUMN like_loaded REAL DEFAULT 0")
        except Exception:
            pass
        # إنشاء recharge_log للقواعد القديمة إن لم يكن موجوداً
        db.execute("""
            CREATE TABLE IF NOT EXISTS recharge_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER,
                code       TEXT,
                amount_sar REAL,
                amount_usd REAL,
                service    TEXT DEFAULT 'sawa',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()

        # ── دمج sawa_loaded في balance بأثر رجعي (مرة واحدة فقط) ──────────
        already = db.execute(
            "SELECT value FROM settings WHERE key='sawa_balance_merged'"
        ).fetchone()
        if not already:
            db.execute(
                "UPDATE users SET balance = balance + sawa_loaded WHERE sawa_loaded > 0"
            )
            # أنشئ recharge_log لبطاقات سوا القديمة المعتمدة التي ليس لها سجل
            rate_row = db.execute(
                "SELECT value FROM settings WHERE key='rate_sawa'"
            ).fetchone()
            rate = float(rate_row[0]) if rate_row else 23.0
            orphans = db.execute("""
                SELECT pc.id, pc.user_id, pc.code, pc.amount, pc.created_at
                FROM   pending_cards pc
                LEFT   JOIN recharge_log rl
                         ON rl.user_id = pc.user_id AND rl.code = pc.code
                WHERE  pc.card_type = 'sawa'
                  AND  pc.status    = 'approved'
                  AND  pc.amount    > 0
                  AND  rl.id IS NULL
            """).fetchall()
            for _pid, uid, code, amount_usd, created_at in orphans:
                amount_sar = round(amount_usd * 100 / rate, 1)
                db.execute(
                    "INSERT INTO recharge_log"
                    "(user_id,code,amount_sar,amount_usd,service,created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (uid, code, amount_sar, amount_usd, "sawa", created_at)
                )
            db.execute(
                "INSERT OR REPLACE INTO settings(key,value) VALUES('sawa_balance_merged','1')"
            )
            db.commit()


# ── أسعار البطاقات (من جدول settings) ───────────────

def get_card_rate(card_type: str) -> float:
    """card_type = 'sawa' أو 'like' → يعيد معدل التحويل (كل 100 ريال = X دولار)"""
    key = f"rate_{card_type}"
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return float(row[0]) if row else 23.0


def set_card_rate(card_type: str, value: float):
    key = f"rate_{card_type}"
    with connect() as db:
        db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
        db.commit()


# ── تتبع الكروت المستخدمة ──────────────────────────

def is_card_used(code: str) -> bool:
    with connect() as db:
        return bool(db.execute(
            "SELECT 1 FROM used_cards WHERE code=?", (code,)
        ).fetchone())


def mark_card_used(code: str, user_id: int):
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO used_cards(code,user_id) VALUES(?,?)",
            (code, user_id)
        )
        db.commit()


# ── البطاقات المعلقة (pending) ───────────────────────

def add_pending_card(user_id: int, card_type: str, code: str) -> int:
    with connect() as db:
        cur = db.execute(
            "INSERT INTO pending_cards(user_id,card_type,code) VALUES(?,?,?)",
            (user_id, card_type, code)
        )
        db.commit()
        return cur.lastrowid


def get_pending_card(card_id: int):
    with connect() as db:
        return db.execute(
            "SELECT id,user_id,card_type,code,status,amount FROM pending_cards WHERE id=?",
            (card_id,)
        ).fetchone()


def update_pending_card(card_id: int, status: str, amount: float = 0.0):
    with connect() as db:
        db.execute(
            "UPDATE pending_cards SET status=?, amount=? WHERE id=?",
            (status, amount, card_id)
        )
        db.commit()


# ── الحد اليومي للشحن ────────────────────────────────

def add_daily_usage(user_id: int, amount_usd: float):
    import datetime
    today = str(datetime.date.today())
    with connect() as db:
        db.execute(
            "INSERT INTO card_daily(user_id,date_str,amount) VALUES(?,?,?) "
            "ON CONFLICT(user_id,date_str) DO UPDATE SET amount=amount+?",
            (user_id, today, amount_usd, amount_usd)
        )
        db.commit()


def get_daily_usage(user_id: int) -> float:
    import datetime
    today = str(datetime.date.today())
    with connect() as db:
        row = db.execute(
            "SELECT amount FROM card_daily WHERE user_id=? AND date_str=?",
            (user_id, today)
        ).fetchone()
        return float(row[0]) if row else 0.0


# ── نظام نقاط الخطورة (Risk Score) ──────────────────

RISK_LIMIT = 100

def add_risk(user_id: int, points: int):
    with connect() as db:
        db.execute(
            "INSERT INTO risk_scores(user_id,score) VALUES(?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET score=score+?, updated_at=CURRENT_TIMESTAMP",
            (user_id, points, points)
        )
        db.commit()


def get_risk(user_id: int) -> int:
    with connect() as db:
        row = db.execute(
            "SELECT score FROM risk_scores WHERE user_id=?", (user_id,)
        ).fetchone()
        return int(row[0]) if row else 0


def reset_risk(user_id: int):
    with connect() as db:
        db.execute(
            "INSERT INTO risk_scores(user_id,score) VALUES(?,0) "
            "ON CONFLICT(user_id) DO UPDATE SET score=0",
            (user_id,)
        )
        db.commit()


def is_risky(user_id: int) -> bool:
    return get_risk(user_id) >= RISK_LIMIT


def get_all_risk_scores() -> list:
    with connect() as db:
        return db.execute(
            "SELECT user_id, score FROM risk_scores WHERE score > 0 ORDER BY score DESC LIMIT 20"
        ).fetchall()


# ── باقات STC (تُنشأ في seed_stc_packages) ──────────

STC_PACKAGES = [
    {"name": "سوا 15",             "price": 4.05},
    {"name": "سوا بيسك",           "price": 8.10},
    {"name": "سوا فليكس 65",       "price": 17.55},
    {"name": "سوا لايك بلس",       "price": 20.25},
    {"name": "سوا كابتن",          "price": 26.39},
    {"name": "سوا فليكس 100",      "price": 27.00},
    {"name": "فليكس سوريا",        "price": 27.00},
    {"name": "فليكس سريلانكا",     "price": 27.00},
    {"name": "سوا بيسك 3 أشهر",   "price": 27.95},
    {"name": "سوا شير",            "price": 31.05},
    {"name": "سوا شير بلس",        "price": 31.05},
    {"name": "سوا 150",            "price": 40.50},
    {"name": "سوا فليكس 150",      "price": 40.50},
    {"name": "سوا بوست بلس",       "price": 45.90},
    {"name": "سوا 175",            "price": 47.25},
    {"name": "سوا فليكس 240",      "price": 64.80},
    {"name": "سوا ستار بلس",       "price": 64.80},
    {"name": "سوا لايك بلس 3 أشهر","price": 69.86},
    {"name": "سوا هيرو",           "price": 97.20},
]


def seed_stc_packages():
    """يُدرج باقات STC مرة واحدة فقط."""
    with connect() as db:
        exists = db.execute(
            "SELECT COUNT(*) FROM services WHERE category='stc'"
        ).fetchone()[0]
        if exists:
            return
        for p in STC_PACKAGES:
            db.execute(
                "INSERT INTO services(category,name,value,price_usd) VALUES('stc',?,?,?)",
                (p["name"], p["name"], p["price"])
            )
        db.commit()


# ════════════════════════════════════════════════
# ── رصيد البطاقات المُشحونة ──────────────────────
# ════════════════════════════════════════════════

def add_card_loaded(uid: int, card_type: str, amount_usd: float):
    """يُضاف مبلغ الشحن إلى عداد sawa_loaded أو like_loaded."""
    col = "sawa_loaded" if card_type == "sawa" else "like_loaded"
    with connect() as db:
        db.execute(f"UPDATE users SET {col}={col}+? WHERE user_id=?", (amount_usd, uid))
        db.commit()


def get_card_loaded(uid: int) -> tuple:
    """يعيد (sawa_loaded, like_loaded) للمستخدم."""
    with connect() as db:
        row = db.execute(
            "SELECT COALESCE(sawa_loaded,0), COALESCE(like_loaded,0) FROM users WHERE user_id=?",
            (uid,)
        ).fetchone()
        return (row[0], row[1]) if row else (0.0, 0.0)


# ════════════════════════════════════════════════
# ── طلبات السحب ──────────────────────────────────
# ════════════════════════════════════════════════

def add_withdrawal(uid: int, country: str, method: str, info: str) -> int:
    """يُنشئ طلب سحب ويعيد ID الطلب."""
    with connect() as db:
        cur = db.execute(
            "INSERT INTO withdrawals(user_id,country,method,info) VALUES(?,?,?,?)",
            (uid, country, method, info)
        )
        db.commit()
        return cur.lastrowid


def get_withdrawal(wid: int):
    """يعيد صف طلب السحب."""
    with connect() as db:
        db.row_factory = __import__("sqlite3").Row
        return db.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()


def update_withdrawal(wid: int, status: str, amount_usd: float = 0):
    with connect() as db:
        db.execute(
            "UPDATE withdrawals SET status=?, amount_usd=? WHERE id=?",
            (status, amount_usd, wid)
        )
        db.commit()


def get_total_card_balance(uid: int) -> float:
    """إجمالي رصيد البطاقات (سوا + لايك) بالدولار."""
    sawa, like = get_card_loaded(uid)
    return sawa + like


def deduct_card_balance(uid: int, amount_usd: float):
    """يخصم amount_usd من رصيد البطاقات (سوا أولاً ثم لايك) ثم من الرصيد الرئيسي."""
    sawa, like = get_card_loaded(uid)
    sawa_deduct = min(sawa, amount_usd)
    like_deduct = min(like, amount_usd - sawa_deduct)
    with connect() as db:
        db.execute(
            "UPDATE users SET sawa_loaded=sawa_loaded-?, like_loaded=like_loaded-? WHERE user_id=?",
            (sawa_deduct, like_deduct, uid)
        )
        db.commit()
    remove_balance(uid, amount_usd, "سحب رصيد البطاقات", "سحب")


def get_card_history(uid: int, limit: int = 10):
    """آخر N طلبات بطاقات للمستخدم — يشمل amount_sar من recharge_log إن وُجد."""
    with connect() as db:
        return db.execute(
            "SELECT pc.id, pc.card_type, pc.status, pc.amount, pc.created_at, "
            "       COALESCE(rl.amount_sar, 0) AS amount_sar "
            "FROM pending_cards pc "
            "LEFT JOIN recharge_log rl "
            "       ON rl.user_id = pc.user_id AND rl.code = pc.code "
            "WHERE pc.user_id = ? "
            "GROUP BY pc.id ORDER BY pc.id DESC LIMIT ?",
            (uid, limit)
        ).fetchall()


def get_order_group() -> int:
    """يعيد معرف مجموعة الطلبات (0 إذا لم تُحدَّد)."""
    with connect() as db:
        row = db.execute(
            "SELECT value FROM settings WHERE key='order_group_id'"
        ).fetchone()
        return int(row[0]) if row else 0


def set_order_group(group_id: int):
    """يحفظ معرف مجموعة الطلبات."""
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES('order_group_id',?)",
            (group_id,)
        )
        db.commit()


# ══════════════════════════════════════════════════
# VIP System + Daily Offers — migrations
# ══════════════════════════════════════════════════

def _migrate_vip_offers():
    """يضيف أعمدة VIP وجداول العروض والإعدادات إن لم تكن موجودة."""
    with connect() as db:
        # تحديث معدل النجوم في جدول prices (100 نجمة = 1.3$)
        db.execute(
            "INSERT OR REPLACE INTO prices(service, price) VALUES('stars_per_usd', ?)",
            (round(100 / 1.3, 4),)
        )
        # أعمدة VIP في جدول المستخدمين
        for sql in [
            "ALTER TABLE users ADD COLUMN total_spent REAL DEFAULT 0.0",
            "ALTER TABLE users ADD COLUMN vip_level TEXT DEFAULT 'normal'",
        ]:
            try:
                db.execute(sql)
            except Exception:
                pass

        db.executescript("""
        CREATE TABLE IF NOT EXISTS vip_settings (
            level      TEXT PRIMARY KEY,
            min_spent  REAL DEFAULT 0,
            discount   REAL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS daily_offers (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            text       TEXT    NOT NULL,
            active     INTEGER DEFAULT 1,
            created_at TEXT    DEFAULT (datetime('now'))
        );
        """)

        # قيم VIP افتراضية
        for level, min_spent, discount in [
            ("normal", 0,   0.00),
            ("mid",    150, 0.05),
            ("vip",    500, 0.10),
        ]:
            db.execute(
                "INSERT OR IGNORE INTO vip_settings(level,min_spent,discount) VALUES(?,?,?)",
                (level, min_spent, discount)
            )
        db.commit()


# ── VIP helpers ─────────────────────────────────

def get_vip_settings() -> list:
    with connect() as db:
        return db.execute(
            "SELECT level, min_spent, discount FROM vip_settings ORDER BY min_spent"
        ).fetchall()


def get_vip_level_for(total_spent: float) -> str:
    """يحدد مستوى VIP بناءً على إجمالي الإنفاق."""
    with connect() as db:
        rows = db.execute(
            "SELECT level, min_spent FROM vip_settings ORDER BY min_spent DESC"
        ).fetchall()
    for row in rows:
        if total_spent >= row[1]:  # row[1] = min_spent
            return row[0]          # row[0] = level
    return "normal"


def get_vip_discount(level: str) -> float:
    with connect() as db:
        row = db.execute(
            "SELECT discount FROM vip_settings WHERE level=?", (level,)
        ).fetchone()
    return row[0] if row else 0.0


def get_user_vip_info(uid: int) -> dict:
    """يجلب بيانات VIP المستخدم بشكل سريع للـ AI."""
    with connect() as db:
        row = db.execute(
            "SELECT balance, total_spent, vip_level FROM users WHERE user_id=?",
            (uid,)
        ).fetchone()
        ref_count = db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (uid,)
        ).fetchone()[0]
    if not row:
        return {}
    return {
        "balance":     row["balance"]     or 0.0,
        "total_spent": row["total_spent"] or 0.0,
        "vip_level":   row["vip_level"]   or "normal",
        "ref_count":   ref_count,
    }


def get_user_vip(user_id: int) -> tuple:
    """يعيد (total_spent, vip_level, discount)."""
    with connect() as db:
        row = db.execute(
            "SELECT total_spent, vip_level FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
    if not row:
        return (0.0, "normal", 0.0)
    total  = row[0] or 0.0
    level  = row[1] or "normal"
    disc   = get_vip_discount(level)
    return (total, level, disc)


def vip_progress_text(user_id: int) -> str:
    """نص شريط تقدم VIP للمستخدم."""
    total, level, _ = get_user_vip(user_id)
    settings = get_vip_settings()
    for i, s in enumerate(settings):
        lvl, min_s, _ = s[0], s[1], s[2]
        if lvl == level and i + 1 < len(settings):
            nxt_lvl, nxt_min, _ = settings[i + 1]
            remaining = max(0, nxt_min - total)
            bars  = int((total - min_s) / max(1, nxt_min - min_s) * 10)
            bar   = "█" * bars + "░" * (10 - bars)
            return (
                f"📊 [{bar}] {total:.1f}$ / {nxt_min}$\n"
                f"باقي <b>{remaining:.1f}$</b> للوصول إلى المستوى التالي"
            )
    return "💎 أنت في أعلى مستوى VIP!"


def set_vip_discount(level: str, discount: float):
    with connect() as db:
        db.execute(
            "UPDATE vip_settings SET discount=? WHERE level=?", (discount, level)
        )
        db.commit()


def set_vip_min_spent(level: str, min_spent: float):
    with connect() as db:
        db.execute(
            "UPDATE vip_settings SET min_spent=? WHERE level=?", (min_spent, level)
        )
        db.commit()


# ── Daily Offers ──────────────────────────────────

def add_daily_offer(text: str):
    with connect() as db:
        db.execute("INSERT INTO daily_offers(text) VALUES(?)", (text,))
        db.commit()


def get_active_offers() -> list:
    with connect() as db:
        return db.execute(
            "SELECT id, text FROM daily_offers WHERE active=1 ORDER BY id DESC"
        ).fetchall()


def get_all_offers() -> list:
    with connect() as db:
        return db.execute(
            "SELECT id, text, active FROM daily_offers ORDER BY id DESC"
        ).fetchall()


def toggle_offer(offer_id: int):
    with connect() as db:
        db.execute(
            "UPDATE daily_offers SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?",
            (offer_id,)
        )
        db.commit()


# ── ذاكرة AI ─────────────────────────────────────────────

import json as _json


def get_ai_history(user_id: int) -> list:
    with connect() as db:
        row = db.execute(
            "SELECT history FROM ai_memory WHERE user_id=?", (user_id,)
        ).fetchone()
        if row:
            try:
                return _json.loads(row["history"])
            except Exception:
                return []
        return []


def save_ai_history(user_id: int, history: list):
    with connect() as db:
        db.execute(
            """INSERT OR REPLACE INTO ai_memory(user_id, history, updated_at)
               VALUES(?, ?, datetime('now'))""",
            (user_id, _json.dumps(history, ensure_ascii=False)),
        )
        db.commit()


def clear_ai_history(user_id: int):
    with connect() as db:
        db.execute("DELETE FROM ai_memory WHERE user_id=?", (user_id,))
        db.commit()


def log_suspicious(user_id: int, message: str):
    with connect() as db:
        db.execute(
            "INSERT INTO ai_suspicious(user_id, message) VALUES(?,?)",
            (user_id, message[:1000]),
        )
        db.commit()


def get_suspicious_logs(limit: int = 20) -> list:
    with connect() as db:
        return db.execute(
            "SELECT * FROM ai_suspicious ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()


def get_user_activity_summary(user_id: int) -> dict:
    """يجمع كل نشاط المستخدم لتلخيصه عبر AI."""
    with connect() as db:
        user = db.execute(
            "SELECT * FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if not user:
            return {}

        orders = db.execute(
            "SELECT service, details, amount, status, created_at "
            "FROM orders WHERE user_id=? ORDER BY id DESC LIMIT 30",
            (user_id,),
        ).fetchall()

        tickets = db.execute(
            "SELECT message, reply, status, created_at "
            "FROM support WHERE user_id=? ORDER BY id DESC LIMIT 10",
            (user_id,),
        ).fetchall()

        try:
            withdrawals = db.execute(
                "SELECT amount, status, created_at FROM withdrawals "
                "WHERE user_id=? ORDER BY id DESC LIMIT 10",
                (user_id,),
            ).fetchall()
        except Exception:
            withdrawals = []

        try:
            cards = db.execute(
                "SELECT card_type, amount_sar, status, created_at "
                "FROM pending_cards WHERE user_id=? ORDER BY id DESC LIMIT 10",
                (user_id,),
            ).fetchall()
        except Exception:
            cards = []

        ref_count = db.execute(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user_id,)
        ).fetchone()[0]

        warnings_val = user["warnings"] if "warnings" in user.keys() else 0

        return {
            "user_id":    user_id,
            "username":   user["username"],
            "balance":    user["balance"],
            "currency":   user["currency"],
            "is_banned":  user["is_banned"],
            "warnings":   warnings_val,
            "orders":     [dict(o) for o in orders],
            "tickets":    [dict(t) for t in tickets],
            "withdrawals": [dict(w) for w in withdrawals],
            "cards":      [dict(c) for c in cards],
            "ref_count":  ref_count,
        }


def delete_offer(offer_id: int):
    with connect() as db:
        db.execute("DELETE FROM daily_offers WHERE id=?", (offer_id,))
        db.commit()


def delete_all_offers():
    with connect() as db:
        db.execute("DELETE FROM daily_offers")
        db.commit()


# ── إعدادات الحساب المساعد (Telethon / @stc25bot) ──────────────────────────

def get_setting(key: str) -> str | None:
    """يقرأ قيمة مفتاح من جدول settings."""
    with connect() as db:
        row = db.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row[0] if row else None


def set_setting(key: str, value: str):
    """يحفظ أو يحدّث قيمة مفتاح في جدول settings."""
    with connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",
            (key, value)
        )
        db.commit()


# ── سجل الشحن (recharge_log) ───────────────────────────────────────────────

def add_recharge_log(user_id: int, code: str, amount_sar: float,
                     amount_usd: float, service: str = "sawa"):
    """يُسجّل عملية شحن ناجحة في recharge_log."""
    with connect() as db:
        db.execute(
            "INSERT INTO recharge_log(user_id,code,amount_sar,amount_usd,service) "
            "VALUES(?,?,?,?,?)",
            (user_id, code, amount_sar, amount_usd, service)
        )
        db.commit()


def get_recharge_log(user_id: int, limit: int = 10) -> list:
    """آخر N عملية شحن للمستخدم."""
    with connect() as db:
        return db.execute(
            "SELECT id, code, amount_sar, amount_usd, service, created_at "
            "FROM recharge_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()


def get_all_recharge_log(limit: int = 50) -> list:
    """آخر N عملية شحن لكل المستخدمين (للأدمن)."""
    with connect() as db:
        return db.execute(
            "SELECT id, user_id, code, amount_sar, amount_usd, service, created_at "
            "FROM recharge_log ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()


# ── Fragment Orders (نجوم / بريميوم تلقائي) ────────────────────────────────

def _ensure_fragment_orders():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS fragment_orders (
                id          INTEGER PRIMARY KEY,   -- نفس id من orders
                user_id     INTEGER,
                svc         TEXT,                  -- 'stars' | 'premium'
                username    TEXT,
                label       TEXT,
                amount_usd  REAL DEFAULT 0,
                amount      INTEGER DEFAULT 0,     -- كمية النجوم
                duration    TEXT DEFAULT '',       -- مدة البريميوم
                status      TEXT DEFAULT 'queued', -- queued|processing|success|manual|refunded
                retry_count INTEGER DEFAULT 0,
                error_msg   TEXT DEFAULT '',
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.commit()

_ensure_fragment_orders()


def add_fragment_order(order_id: int, user_id: int, svc: str, username: str,
                       label: str, amount_usd: float,
                       amount: int = 0, duration: str = "") -> None:
    with connect() as db:
        db.execute(
            "INSERT OR IGNORE INTO fragment_orders"
            "(id,user_id,svc,username,label,amount_usd,amount,duration) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (order_id, user_id, svc, username, label, amount_usd, amount, duration)
        )
        db.commit()


def get_fragment_order(order_id: int):
    with connect() as db:
        return db.execute(
            "SELECT * FROM fragment_orders WHERE id=?", (order_id,)
        ).fetchone()


def update_fragment_order(order_id: int, status: str, error_msg: str = ""):
    with connect() as db:
        db.execute(
            "UPDATE fragment_orders "
            "SET status=?, error_msg=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE id=?",
            (status, error_msg, order_id)
        )
        db.commit()


def get_pending_fragment_orders(limit: int = 20) -> list:
    """طلبات Fragment التي تحتاج تنفيذ يدوي."""
    with connect() as db:
        return db.execute(
            "SELECT id, user_id, svc, username, label, amount_usd, status, created_at "
            "FROM fragment_orders WHERE status IN ('manual','queued') "
            "ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()

# ===== دمج الرصيد العام + البطاقات =====

def get_cards_balance(user_id: int):
    with connect() as db:
        row = db.execute(
            "SELECT SUM(amount) FROM pending_cards WHERE user_id=?",
            (user_id,)
        ).fetchone()
    return row[0] if row and row[0] else 0.0


def get_total_balance(user_id: int):
    return get_balance(user_id) + get_cards_balance(user_id)

def remove_cards_balance(user_id: int, amount: float):
    cards = get_cards_balance(user_id)

    if cards < amount:
        return False

    with connect() as db:
        # نجيب كل البطاقات للمستخدم
        rows = db.execute(
            "SELECT id, amount FROM pending_cards WHERE user_id=? ORDER BY id",
            (user_id,)
        ).fetchall()

        remaining = amount

        for row in rows:
            card_id = row["id"]
            card_amount = row["amount"]

            if remaining <= 0:
                break

            if card_amount <= remaining:
                # نحذف الكرت كامل
                db.execute(
                    "DELETE FROM pending_cards WHERE id=?",
                    (card_id,)
                )
                remaining -= card_amount
            else:
                # ننقص جزء من الكرت
                db.execute(
                    "UPDATE pending_cards SET amount = amount - ? WHERE id=?",
                    (remaining, card_id)
                )
                remaining = 0

        db.commit()

    return True

