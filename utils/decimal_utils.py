"""
Decimal Utils — formatting helpers for USDT amounts.
Never use float for monetary values.
"""
from decimal import Decimal, ROUND_DOWN


def fmt_usdt(amount: Decimal, decimals: int = 8) -> str:
    """Format USDT amount: 0.00150000"""
    quantizer = Decimal(10) ** -decimals
    return str(amount.quantize(quantizer, rounding=ROUND_DOWN))


def fmt_usdt_short(amount: Decimal) -> str:
    """Format USDT with trailing zero removal: 0.0015"""
    return f"{amount:.8f}".rstrip("0").rstrip(".")


def parse_usdt(value: str) -> Decimal:
    """Parse user-supplied USDT string to Decimal. Raises ValueError on invalid input."""
    try:
        d = Decimal(value.strip().replace(",", ""))
        if d < 0:
            raise ValueError("Amount must be positive")
        return d
    except Exception:
        raise ValueError(f"Invalid amount: {value!r}")


def safe_decimal(value) -> Decimal:
    """Safely convert any value to Decimal."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")
