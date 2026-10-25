"""Display-layer tests (markdown escaping, readable bill, promo wording)."""

from __future__ import annotations

from datetime import date

from tripstack.engine.comparison import build_comparison_result
from tripstack.ui_format import NO_CASHBACK, bill_rows, md, promo_line

from .helpers import TODAY, cashback, instant, offer


def test_md_escapes_dollar_signs():
    """Two amounts on one line would otherwise be parsed as LaTeX math."""
    text = md("Upfront: $554.40 -> Net: $554.40")
    assert text == "Upfront: \\$554.40 -> Net: \\$554.40"
    # Every remaining '$' is escaped, so LaTeX sees no opening delimiter.
    assert text.count("$") == text.count("\\$")


def test_bill_hides_eligible_spend_when_there_is_no_cashback():
    o = offer(base="492.80", taxes="61.60", fees="25.00")
    result = build_comparison_result(o, [], today=TODAY)
    rows = dict(bill_rows(result, "USD"))
    assert rows["Cashback"] == NO_CASHBACK
    assert "Cashback-eligible spend" not in rows
    assert rows["List price (before offers)"] == "$579.40"


def test_bill_shows_eligible_spend_when_cashback_applies():
    o = offer(base="850.00", taxes="100.00", fees="25.00")
    promo = cashback(platform="Provider A", rate="0.08", cap="30.00")
    result = build_comparison_result(o, [promo], today=TODAY)
    rows = dict(bill_rows(result, "USD"))
    assert result.estimated_cashback > 0
    assert rows["Cashback-eligible spend"] == "$850.00"
    assert rows["Estimated cashback"] == "−$30.00"
    assert rows["Upfront payment (due today)"] == "$975.00"


def test_bill_shows_instant_discount_only_when_present():
    o = offer(base="300.00", taxes="0", fees="0")
    with_discount = build_comparison_result(
        o, [instant(fixed="25.00", minimum_spend=None)], today=TODAY
    )
    assert "Instant discount" in dict(bill_rows(with_discount, "USD"))

    without = build_comparison_result(o, [], today=TODAY)
    assert "Instant discount" not in dict(bill_rows(without, "USD"))


def test_promo_line_is_readable_and_hides_internal_ids():
    promo = cashback(
        promo_id="promo-a-cashback-8", rate="0.08", cap="30.00", minimum_spend="100.00"
    )
    line = promo_line(promo, "USD")
    assert "promo-a-cashback-8" not in line
    assert "8% back" in line
    assert "capped at $30.00" in line
    assert "min spend $100.00" in line
    assert "status: estimated" in line

    fixed = instant(fixed="25.00", minimum_spend="200.00")
    assert "$25.00 off" in promo_line(fixed, "USD")


def test_bill_amounts_are_formatted_strings_not_floats():
    o = offer(base="100.00", taxes="10.00", fees="5.00")
    result = build_comparison_result(o, [], today=TODAY)
    money_rows = 0
    for _item, amount in bill_rows(result, "USD"):
        assert isinstance(amount, str)
        if amount == NO_CASHBACK:
            continue
        assert amount.startswith("$") or amount.startswith("−$")
        money_rows += 1
    assert money_rows >= 5
    assert date.today() >= TODAY  # sanity: helpers use a fixed "today"
