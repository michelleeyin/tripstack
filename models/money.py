"""Shared money helpers.

Every monetary value in TripStack is a :class:`decimal.Decimal` quantized to
two decimal places. Floats are never used for money because binary floating
point cannot represent cent values exactly, which produces off-by-a-cent
errors when caps and percentages are applied.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_money(value: Any) -> Decimal:
    """Coerce ``value`` into a two-decimal Decimal.

    ``str`` conversion is used deliberately: ``Decimal(0.08)`` yields
    0.0800000000000000016..., while ``Decimal("0.08")`` is exact.
    """
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    if isinstance(value, bool):
        return ZERO
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


RATE_PLACES = Decimal("0.000001")


def to_rate(value: Any) -> Decimal:
    """Coerce a fractional rate (0.075 == 7.5%) without cent rounding.

    Money is quantized to cents; rates are not. Rounding a rate to two
    decimals silently turns 7.5% into 8% — on a $1,000 booking that is
    $80 of cashback instead of $75.
    """
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value.quantize(RATE_PLACES, rounding=ROUND_HALF_UP)
    return Decimal(str(value)).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def max_zero(value: Decimal) -> Decimal:
    """Clamp to zero — a discount may never make a payment negative."""
    return value if value > ZERO else ZERO


def fmt_money(value: Decimal | None, currency: str = "USD") -> str:
    if value is None:
        return "—"
    symbol = {"USD": "$", "EUR": "€", "GBP": "£", "CNY": "¥"}.get(currency, "")
    return f"{symbol}{value:,.2f}"
