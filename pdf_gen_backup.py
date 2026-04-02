"""
مولّد PDF عربي — weasyprint + pango + Cairo font
pango مثبّت كحزمة نظام → العربية تظهر صحيحة بدون reshaper
"""
import os
import io
import logging
from datetime import datetime

log = logging.getLogger(__name__)

FONT_PATH = os.path.join(os.path.dirname(__file__), "fonts", "Cairo-Regular.ttf")


def _font_url() -> str:
    """مسار الخط كـ URL مناسب لـ @font-face."""
    return FONT_PATH.replace("\\", "/")


def _build_html(uid: int, u: dict, txs: list) -> str:
    """
    يبني HTML كامل لكشف الحساب — يقرأ من جدول transactions فقط.
    amount > 0 → له (عمود أخضر)   |   amount < 0 → عليه (عمود أحمر)
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

    def _loc(usd_val: float) -> str:
        """يُحوّل مبلغ USD للعرض بعملة العميل مع الإبقاء على الدولار مرجعاً."""
        abs_val = abs(usd_val)
        loc_val = _convert(abs_val, cur)
        usd_str = f"{abs_val:.4f}$"
        if cur == "USD":
            return usd_str
        if cur == "YER":
            loc_str = f"{loc_val:,.0f} {cur}"
        else:
            loc_str = f"{loc_val:,.2f} {cur}"
        return f"{loc_str} (≈ {usd_str})"

    bal_loc     = _convert(bal_usd, cur)
    bal_loc_str = f"{bal_loc:,.0f} {cur}" if cur == "YER" else f"{bal_loc:,.2f} {cur}"
    bal_usd_str = f"{bal_usd:.4f}$"
    bal_display = bal_loc_str if cur == "USD" else f"{bal_loc_str} (≈ {bal_usd_str})"

    total_in    = sum(t.get("amount", 0) for t in txs if (t.get("amount") or 0) > 0)
    total_out   = sum(abs(t.get("amount", 0)) for t in txs if (t.get("amount") or 0) < 0)
    tin_loc     = _convert(total_in, cur)
    tout_loc    = _convert(total_out, cur)
    fmt         = ("{:,.0f}" if cur == "YER" else "{:,.2f}").format

    tx_rows = ""
    for t in txs[:300]:
        amt       = t.get("amount") or 0
        note      = str(t.get("note") or t.get("type") or "—")[:45]
        date      = str(t.get("created_at") or "")[:16]
        bal_after = t.get("balance_after") or 0

        amt_display      = _loc(amt)
        bal_after_display = _loc(bal_after)

        if amt > 0:
            in_val  = f'<span style="color:#34d399;font-weight:bold">+{amt_display}</span>'
            out_val = "—"
        else:
            in_val  = "—"
            out_val = f'<span style="color:#f87171;font-weight:bold">-{amt_display}</span>'

        tx_rows += f"""
        <tr>
            <td>{in_val}</td>
            <td>{out_val}</td>
            <td class="svc">{note}</td>
            <td>{date}</td>
            <td style="color:#94a3b8;font-size:11px">{bal_after_display}</td>
        </tr>"""

    all_rows = tx_rows

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<style>
@font-face {{
    font-family: 'Cairo';
    src: url('{_font_url()}');
}}

* {{
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}}

body {{
    font-family: 'Cairo', 'DejaVu Sans', sans-serif;
    direction: rtl;
    text-align: right;
    background: #0f172a;
    color: #e2e8f0;
    padding: 24px;
    font-size: 13px;
    line-height: 1.6;
}}

/* ── رأس الصفحة ── */
.header {{
    text-align: center;
    border-bottom: 2px solid #334155;
    padding-bottom: 14px;
    margin-bottom: 18px;
}}
.header h1 {{
    font-size: 22px;
    color: #38bdf8;
    margin-bottom: 4px;
}}
.header p {{
    color: #64748b;
    font-size: 12px;
}}

/* ── بطاقة الرصيد ── */
.balance-card {{
    background: linear-gradient(135deg, #1e3a5f, #0f172a);
    border: 1px solid #334155;
    border-radius: 10px;
    padding: 16px 22px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.balance-card .lbl {{
    color: #64748b;
    font-size: 12px;
}}
.balance-card .amount {{
    font-size: 24px;
    color: #38bdf8;
    font-weight: bold;
}}
.balance-card .local {{
    color: #94a3b8;
    font-size: 12px;
}}

/* ── معلومات الحساب ── */
.info-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 20px;
    background: #1e293b;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 14px;
}}
.info-item .lbl {{
    color: #64748b;
    font-size: 11px;
}}
.info-item .val {{
    color: #e2e8f0;
    font-size: 13px;
    font-weight: bold;
}}

/* ── الجدول الرئيسي ── */
h2 {{
    color: #38bdf8;
    font-size: 14px;
    margin-bottom: 10px;
    padding-bottom: 4px;
    border-bottom: 1px solid #334155;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 22px;
}}

thead th {{
    background: #1e293b;
    color: #94a3b8;
    font-size: 11px;
    padding: 9px 10px;
    text-align: right;
    border-bottom: 1px solid #334155;
}}

tbody tr {{
    border-bottom: 1px solid #1e293b;
}}

tbody tr:nth-child(even) {{
    background: #0d1829;
}}

tbody tr:nth-child(odd) {{
    background: #0f172a;
}}

tbody td {{
    padding: 8px 10px;
    text-align: right;
    vertical-align: middle;
    color: #cbd5e1;
    font-size: 12px;
}}

td.svc {{
    color: #e2e8f0;
    max-width: 220px;
}}

.oid {{
    color: #475569;
    font-size: 11px;
    margin-right: 4px;
}}

/* ── تذييل ── */
.footer {{
    text-align: center;
    color: #334155;
    font-size: 11px;
    border-top: 1px solid #1e293b;
    padding-top: 10px;
    margin-top: 10px;
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
        <div class="amount">{bal_display}</div>
    </div>
    <div style="text-align:left">
        <div class="lbl">معرّف العميل</div>
        <div class="val" style="color:#94a3b8;font-size:14px">{uid}</div>
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
            <th style="color:#f87171">عليه (خصم/شراء)</th>
            <th>البيان</th>
            <th>التاريخ</th>
            <th>رصيد بعد</th>
        </tr>
    </thead>
    <tbody>
        {all_rows if all_rows else '<tr><td colspan="5" style="text-align:center;color:#475569">لا توجد حركات بعد</td></tr>'}
    </tbody>
</table>

<!-- إجماليات -->
<table>
    <thead>
        <tr>
            <th>إجمالي الإيداعات</th>
            <th>إجمالي الخصومات</th>
            <th>عدد الحركات</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td style="color:#34d399;font-weight:bold">+{fmt(tin_loc)} {cur}</td>
            <td style="color:#f87171;font-weight:bold">-{fmt(tout_loc)} {cur}</td>
            <td style="color:#38bdf8;font-weight:bold">{len(txs)} حركة</td>
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
