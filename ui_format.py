"""Display-layer formatting for the dashboard.

Kept out of ``app.py`` so it can be unit-tested without Streamlit running.
Two rules live here:

1. ``md()`` escapes ``$`` because Streamlit renders markdown and reads a pair
   of ``$...$`` as LaTeX — money amounts would vanish into a math block.
2. The bill shows "not applicable" rather than an engine default whenever no
   cashback offer applied.
"""

from __future__ import annotations

from .models.money import fmt_money
from .models.promotion import Promotion
from .models.result import ComparisonResult

NO_CASHBACK = "Not applicable — no confirmed cashback offer"


def md(text: str) -> str:
    """Escape '$' so `$554.40 ... $554.40` is not parsed as LaTeX."""
    return text.replace("$", "\\$")


def bill_rows(result: ComparisonResult, currency: str = "USD") -> list[tuple[str, str]]:
    """Readable bill. Amounts are pre-formatted strings, not markdown."""
    b = result.breakdown
    rows = [
        ("Room rate", fmt_money(b.base_price, currency)),
        ("Taxes", fmt_money(b.taxes, currency)),
        ("Mandatory fees", fmt_money(b.mandatory_fees, currency)),
        ("List price (before offers)", fmt_money(b.list_price, currency)),
    ]
    if b.instant_discount > 0:
        rows.append(("Instant discount", f"−{fmt_money(b.instant_discount, currency)}"))
    rows.append(("Estimated upfront payment", fmt_money(b.upfront_payment, currency)))
    if result.estimated_cashback > 0:
        rows.append(
            ("Cashback-eligible spend", fmt_money(b.cashback_eligible_spend, currency))
        )
        rows.append(
            ("Estimated cashback", f"−{fmt_money(result.estimated_cashback, currency)}")
        )
    else:
        # The engine defaults this field to the room rate; showing it looks
        # like a real cashback figure when nothing applied.
        rows.append(("Cashback", NO_CASHBACK))
    rows.append(("Estimated net cost", fmt_money(result.estimated_net_cost, currency)))
    rows.append(
        ("Certain cost (verified only)", fmt_money(result.guaranteed_net_cost, currency))
    )
    return rows


def promo_line(p: Promotion, currency: str = "USD") -> str:
    """Human-readable promotion line; internal ids stay in the tech details."""
    if p.rate is not None:
        # normalize() strips the trailing zeros added by rate precision, so
        # 8% prints as "8%" and 7.5% as "7.5%".
        amount = f"{(p.rate * 100).normalize():f}% " + ("back" if p.type == "cashback" else "off")
    else:
        amount = f"{fmt_money(p.fixed_amount, currency)} off"
    bits = [p.type.replace("_", " ").title(), amount]
    if p.minimum_spend is not None:
        bits.append(f"min spend {fmt_money(p.minimum_spend, currency)}")
    if p.cap is not None:
        bits.append(f"capped at {fmt_money(p.cap, currency)}")
    bits.append(f"status: {p.verification_status}")
    return " · ".join(bits)
