@font-face { font-family: 'Arabic'; src: url('file:///usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf'); }
"""
مولّد PDF عربي — weasyprint + Noto Naskh Arabic (Base64 مضمّن)
الخط مُضمَّن مباشرة داخل CSS بدون أي اعتماد على مسارات النظام.
"""
import os
import io
import base64
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# أولوية البحث عن الخط:
# 1) مسار VPS الرسمي   2) النسخة المجمّعة مع البوت   3) Cairo احتياطي
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    os.path.join(os.path.dirname(__file__), "fonts", "NotoNaskhArabic.ttf"),
    os.path.join(os.path.dirname(__file__), "fonts", "Cairo-Regular.ttf"),
]


def _load_font_b64() -> str:
    """
    يبحث عن خط عربي بالترتيب ويُعيده Base64.
    يضمن عمل الخط بدون أي اعتماد على مسارات النظام.
    """
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            log.info(f"✅ PDF font: {path}")
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
    raise FileNotFoundError(
        "❌ لا يوجد خط عربي. ضع NotoNaskhArabic.ttf في مجلد fonts/"
    )


def _build_html(uid: int, u: dict, txs: list) -> str:
    """
    يبني HTML كشف الحساب.
    amount > 0 → له (أخضر)  |  amount < 0 → عليه (أحمر)
    كل مبلغ يظهر بسطرين: العملة الأساسية فوق + الدولار تحته.
    """
    cur     = u.get("currency") or "USD"
    bal_usd = u.get("balance") or 0
    name    = u.get("first_name") or "—"
    uname   = f"@{u['username']}" if u.get("username") else "—"
    vip     = u.get("vip_level") or "عادي"
    total   = u.get("total_spent") or 0
    now_str = datetime.now().strftime("%Y-%m-%d  %H:%M")

    try:
        from db import convert_from_usd
        _convert = convert_from_usd
    except Exception:
        _convert = lambda v, c: v

    # ── دوال تنسيق المبالغ ────────────────────────────
    def _fmt_loc(abs_val: float) -> str:
        """قيمة محلية نصية (بدون إشارة)."""
        loc = _convert(abs_val, cur)
        if cur == "YER":
            return f"{loc:,.0f} {cur}"
        return f"{loc:,.2f} {cur}"

    def _loc_html(usd_val: float, color: str, sign: str = "") -> str:
        """
        سطران: سطر العملة الأساسية (كبير ملوّن) + سطر الدولار (صغير رمادي).
        إذا كانت العملة USD يظهر سطر واحد فقط.
        """
        abs_val = abs(usd_val)
        usd_str = f"{abs_val:.4f}$"
        if cur == "USD":
            return (
                f'<div class="amt-main" style="color:{color}">'
                f'{sign}{usd_str}</div>'
            )
        loc_str = _fmt_loc(abs_val)
        return (
            f'<div class="amt-main" style="color:{color}">{sign}{loc_str}</div>'
            f'<div class="amt-ref">≈ {usd_str}</div>'
        )

    def _loc_single(usd_val: float) -> str:
        """سطر واحد فقط — للأعمدة الضيقة (رصيد بعد)."""
        abs_val = abs(usd_val)
        if cur == "USD":
            return f"{abs_val:.4f}$"
        return _fmt_loc(abs_val)

    # ── الرصيد ────────────────────────────────────────
    bal_usd_str = f"{bal_usd:.4f}$"
    if cur == "USD":
        bal_main = bal_usd_str
        bal_ref  = ""
    else:
        bal_main = _fmt_loc(bal_usd)
        bal_ref  = f'<div class="balance-ref">≈ {bal_usd_str}</div>'

    # ── الإجماليات ────────────────────────────────────
    total_in  = sum(t.get("amount", 0) for t in txs if (t.get("amount") or 0) > 0)
    total_out = sum(abs(t.get("amount", 0)) for t in txs if (t.get("amount") or 0) < 0)
    fmt       = ("{:,.0f}" if cur == "YER" else "{:,.2f}").format
    tin_loc   = _convert(total_in,  cur)
    tout_loc  = _convert(total_out, cur)

    def _total_html(usd_val: float, loc_val: float, color: str, sign: str) -> str:
        usd_str = f"{abs(usd_val):.4f}$"
        if cur == "USD":
            return f'<div class="amt-main" style="color:{color}">{sign}{usd_str}</div>'
        loc_str = f"{fmt(loc_val)} {cur}"
        return (
            f'<div class="amt-main" style="color:{color}">{sign}{loc_str}</div>'
            f'<div class="amt-ref">≈ {usd_str}</div>'
        )

    tin_html  = _total_html(total_in,  tin_loc,  "#34d399", "+")
    tout_html = _total_html(total_out, tout_loc, "#f87171", "-")

    # ── صفوف الجدول ──────────────────────────────────
    tx_rows = ""
    for t in txs[:300]:
        amt       = t.get("amount") or 0
        note      = str(t.get("note") or t.get("type") or "—")[:45]
        date      = str(t.get("created_at") or "")[:16]
        bal_after = t.get("balance_after") or 0
        ba_str    = _loc_single(bal_after)

        if amt > 0:
            in_cell  = _loc_html(amt, "#34d399", "+")
            out_cell = "—"
        else:
            in_cell  = "—"
            out_cell = _loc_html(amt, "#f87171", "-")

        tx_rows += f"""
        <tr>
            <td class="num">{in_cell}</td>
            <td class="num">{out_cell}</td>
            <td class="svc">{note}</td>
            <td class="dt">{date}</td>
            <td class="bal">{ba_str}</td>
        </tr>"""

    font_data = _load_font_b64()

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<style>

/* ── الخط: Noto Naskh Arabic — مضمّن Base64 ── */
@font-face {{
    font-family: 'Arabic';
    src: url('data:font/ttf;base64,{font_data}');
    font-weight: normal;
    font-style: normal;
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body { direction: rtl; text-align: right;{
    font-family: 'Arabic';
    direction: rtl;
    text-align: right;
    background: #0f172a;
    color: #e2e8f0;
    padding: 28px 26px;
    font-size: 14px;
    font-weight: 400;
    line-height: 1.7;
}}

/* ── رأس الصفحة ── */
.header {{
    text-align: center;
    border-bottom: 2px solid #334155;
    padding-bottom: 16px;
    margin-bottom: 22px;
}}
.header h1 {{
    font-size: 26px;
    font-weight: 700;
    color: #38bdf8;
    letter-spacing: 1px;
    margin-bottom: 4px;
}}
.header p {{
    color: #64748b;
    font-size: 12px;
    font-weight: 400;
}}

/* ── بطاقة الرصيد ── */
.balance-card {{
    background: linear-gradient(135deg, #1e3a5f 0%, #0f1e35 100%);
    border: 1px solid #2563eb44;
    border-radius: 12px;
    padding: 20px 26px;
    margin-bottom: 22px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.balance-card .lbl {{
    color: #64748b;
    font-size: 12px;
    font-weight: 400;
    margin-bottom: 4px;
}}
.balance-main {{
    font-size: 28px;
    font-weight: 700;
    color: #38bdf8;
    line-height: 1.2;
}}
.balance-ref {{
    color: #94a3b8;
    font-size: 14px;
    font-weight: 400;
    margin-top: 2px;
}}
.balance-card .val {{
    color: #94a3b8;
    font-size: 15px;
    font-weight: 600;
}}

/* ── معلومات الحساب ── */
.info-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 22px;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 16px;
}}
.info-item .lbl {{
    color: #64748b;
    font-size: 11px;
    font-weight: 400;
    margin-bottom: 2px;
}}
.info-item .val {{
    color: #e2e8f0;
    font-size: 14px;
    font-weight: 600;
}}

/* ── عنوان الجدول ── */
h2 {{
    color: #38bdf8;
    font-size: 15px;
    font-weight: 700;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid #334155;
}}

/* ── الجدول الرئيسي ── */
table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 24px;
}}

thead th {{
    background: #1e293b;
    color: #94a3b8;
    font-size: 12px;
    font-weight: 600;
    padding: 10px 10px;
    text-align: right;
    border-bottom: 2px solid #334155;
}}

tbody tr {{
    border-bottom: 1px solid #1e293b;
}}
tbody tr:nth-child(even) {{ background: #0d1829; }}
tbody tr:nth-child(odd)  {{ background: #0f172a; }}

tbody td {{
    padding: 9px 10px;
    text-align: right;
    vertical-align: middle;
    color: #cbd5e1;
    font-size: 13px;
}}

/* أعمدة المبالغ */
td.num {{
    min-width: 110px;
}}
.amt-main {{
    font-size: 13px;
    font-weight: 700;
    line-height: 1.3;
}}
.amt-ref {{
    font-size: 11px;
    font-weight: 400;
    color: #64748b;
    margin-top: 1px;
}}

/* عمود البيان */
td.svc {{
    color: #e2e8f0;
    font-size: 13px;
    font-weight: 400;
    max-width: 200px;
}}

/* عمود التاريخ */
td.dt {{
    color: #94a3b8;
    font-size: 12px;
    white-space: nowrap;
}}

/* عمود رصيد بعد */
td.bal {{
    color: #94a3b8;
    font-size: 11px;
    font-weight: 400;
}}

/* ── جدول الإجماليات ── */
.totals-table thead th {{
    font-size: 12px;
    font-weight: 600;
    background: #1e293b;
}}
.totals-table tbody td {{
    padding: 12px 10px;
    font-size: 13px;
}}

/* ── تذييل ── */
.footer {{
    text-align: center;
    color: #334155;
    font-size: 11px;
    border-top: 1px solid #1e293b;
    padding-top: 12px;
    margin-top: 8px;
}}
</style>
</head>
<body>

<!-- رأس الصفحة -->
<div class="header">
    <h1>متجر روز 🌹</h1>
    <p>كشف حساب العميل — {now_str}</p>
</div>

<!-- بطاقة الرصيد -->
<div class="balance-card">
    <div>
        <div class="lbl">الرصيد الحالي</div>
        <div class="balance-main">{bal_main}</div>
        {bal_ref}
    </div>
    <div style="text-align:left">
        <div class="lbl">معرّف العميل</div>
        <div class="val" style="color:#94a3b8;font-size:15px;font-weight:600">{uid}</div>
    </div>
</div>

<!-- معلومات الحساب -->
<div class="info-grid">
    <div class="info-item">
        <div class="lbl">الاسم</div>
        <div class="val">{name}</div>
    </div>
    <div class="info-item">
        <div class="lbl">اليوزر</div>
        <div class="val">{uname}</div>
    </div>
    <div class="info-item">
        <div class="lbl">مستوى VIP</div>
        <div class="val">{vip}</div>
    </div>
    <div class="info-item">
        <div class="lbl">عدد الحركات</div>
        <div class="val">{len(txs)} حركة</div>
    </div>
    <div class="info-item">
        <div class="lbl">الإجمالي المُنفق</div>
        <div class="val">{total:.2f}$</div>
    </div>
    <div class="info-item">
        <div class="lbl">العملة</div>
        <div class="val">{cur}</div>
    </div>
</div>

<!-- جدول الحركات -->
<h2>📊 كشف الحركات ({len(txs)} عملية)</h2>
<table>
    <thead>
        <tr>
            <th style="color:#34d399">له (إيداع)</th>
            <th style="color:#f87171">عليه (خصم)</th>
            <th>البيان</th>
            <th>التاريخ</th>
            <th>رصيد بعد</th>
        </tr>
    </thead>
    <tbody>
        {tx_rows if tx_rows else '<tr><td colspan="5" style="text-align:center;color:#475569;padding:20px">لا توجد حركات بعد</td></tr>'}
    </tbody>
</table>

<!-- إجماليات -->
<table class="totals-table">
    <thead>
        <tr>
            <th>إجمالي الإيداعات</th>
            <th>إجمالي الخصومات</th>
            <th>عدد الحركات</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>{tin_html}</td>
            <td>{tout_html}</td>
            <td>
                <div class="amt-main" style="color:#38bdf8">{len(txs)} حركة</div>
            </td>
        </tr>
    </tbody>
</table>

<div class="footer">
    تم إنشاء هذا الكشف تلقائياً — متجر روز 🌹
</div>

</body>
</html>"""


def generate_statement_pdf(uid: int) -> bytes | None:
    """
    يُنشئ PDF كشف حساب المستخدم باستخدام weasyprint.
    يقرأ من جدول transactions فقط — له/عليه حسب إشارة amount.
    يُعيد bytes أو None عند الفشل.
    """
    try:
        from weasyprint import HTML
        from db import get_user, get_transactions

        user = get_user(uid)
        if not user:
            return None

        u   = dict(user)
        txs = [dict(t) for t in get_transactions(uid, limit=300)]

        html_src = _build_html(uid, u, txs)

        pdf_bytes = HTML(
            string=html_src,
            base_url=os.path.dirname(__file__)
        ).write_pdf()

        log.info(f"✅ PDF مُنشأ للمستخدم {uid}: {len(pdf_bytes)} bytes")
        return pdf_bytes

    except Exception as e:
        log.error(f"خطأ في إنشاء PDF للمستخدم {uid}: {e}", exc_info=True)
        return None
