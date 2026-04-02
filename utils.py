from config import CURRENCY_SYMBOLS
from db import get_rate


def fmt_bal(balance_usd: float, currency: str) -> str:
    rate      = get_rate(currency)
    converted = round(balance_usd * rate, 2)
    sym       = CURRENCY_SYMBOLS.get(currency, currency)
    if currency == "YER":
        return f"{converted:,.0f} {sym} | {balance_usd:.4f}$"
    return f"{converted:.2f} {sym} | {balance_usd:.4f}$"


def stars_usd(qty: int) -> float:
    rate = 1.6 if qty >= 1000 else 1.7
    return round((qty / 100) * rate, 4)
