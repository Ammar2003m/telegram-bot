"""
وحدة CryptoPay — دفع تلقائي عبر @CryptoBot
"""

import logging
from aiocryptopay import AioCryptoPay, Networks
from config import CRYPTO_API_TOKEN

log = logging.getLogger(__name__)

_cp: AioCryptoPay | None = None


def _get() -> AioCryptoPay:
    global _cp
    if _cp is None:
        _cp = AioCryptoPay(token=CRYPTO_API_TOKEN, network=Networks.MAIN_NET)
    return _cp


async def create_invoice(uid: int, amount_usd: float, asset: str = "USDT") -> tuple[str, int] | None:
    """
    ينشئ فاتورة CryptoPay.
    يُرجع: (pay_url, invoice_id) أو None عند الفشل.
    """
    try:
        cp  = _get()
        inv = await cp.create_invoice(
            asset=asset,
            amount=round(amount_usd, 4),
            description="شحن رصيد — متجر روز",
            payload=f"{uid}|{amount_usd:.4f}",
            allow_comments=False,
            allow_anonymous=False,
        )
        return inv.bot_invoice_url, inv.invoice_id
    except Exception as e:
        log.error("CryptoPay create_invoice error: %s", e)
        return None


async def get_paid_invoices() -> list:
    """يُرجع قائمة الفواتير المدفوعة."""
    try:
        cp   = _get()
        invs = await cp.get_invoices(status="paid")
        return invs if invs else []
    except Exception as e:
        log.error("CryptoPay get_invoices error: %s", e)
        return []
