"""
Decimal Utils — formatting helpers for USDT amounts.
Never use float for monetary values.
"""
from decimal import Decimal, ROUND_DOWN


def safe_decimal(value) -> Decimal:
    """Safely convert any value (int, float, str, None, Decimal) to Decimal."""
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def fmt_usdt(amount, decimals: int = 8) -> str:
    """Format USDT amount: 0.00150000
    
    Accepts Decimal, int, float, str, or None — always returns a fixed-point string.
    """
    d = safe_decimal(amount)
    quantizer = Decimal(10) ** -decimals
    return str(d.quantize(quantizer, rounding=ROUND_DOWN))


def fmt_usdt_short(amount) -> str:
    """Format USDT with trailing zero removal: 0.0015
    
    Accepts Decimal, int, float, str, or None.
    """
    d = safe_decimal(amount)
    return f"{d:.8f}".rstrip("0").rstrip(".")


def parse_usdt(value: str) -> Decimal:
    """Parse user-supplied USDT string to Decimal. Raises ValueError on invalid input."""
    try:
        d = Decimal(value.strip().replace(",", ""))
        if d < 0:
            raise ValueError("Amount must be positive")
        return d
    except Exception:
        raise ValueError(f"Invalid amount: {value!r}")