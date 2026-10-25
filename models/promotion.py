"""Promotion / cashback rule schema.

Promotions are either curated by hand in ``data/promotion_rules.json`` or
extracted from natural-language terms by the Gemma parser. In both cases the
original text and source URL are preserved so every discount is traceable.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .money import to_money, to_rate

VerificationStatus = Literal["verified", "estimated", "unknown"]
PromotionType = Literal["cashback", "instant_discount", "coupon"]


class Promotion(BaseModel):
    """A discount or cashback rule attached to a booking platform."""

    model_config = ConfigDict(validate_assignment=True)

    promotion_id: str
    platform: str = "*"
    type: PromotionType = "cashback"
    # Percentage benefit, 0.08 == 8%.
    rate: Decimal | None = None
    # Fixed-amount benefit, e.g. $25 off.
    fixed_amount: Decimal | None = None
    # Maximum reward payable under this rule.
    cap: Decimal | None = None
    minimum_spend: Decimal | None = None
    # Whether taxes and mandatory fees count toward cashback-eligible spend.
    taxes_eligible: bool = False
    stackable: bool = False
    valid_until: date | None = None
    source_url: str = ""
    raw_text: str = ""
    verification_status: VerificationStatus = "estimated"
    requires_verification: bool = False
    excluded_categories: list[str] = Field(default_factory=list)
    notes: str = ""

    @field_validator("fixed_amount", "cap", "minimum_spend", mode="before")
    @classmethod
    def _coerce_money(cls, value: object) -> Decimal | None:
        if value is None or value == "":
            return None
        amount = to_money(value)
        if not amount.is_finite() or Decimal(str(value)) < 0:
            raise ValueError("promotion amounts must be finite and non-negative")
        return amount

    @field_validator("rate", mode="before")
    @classmethod
    def _coerce_rate(cls, value: object) -> Decimal | None:
        """Rates are fractions, not money — never quantize them to cents.

        ``to_money`` rounds to two decimals, which turns 0.075 (7.5%) into
        0.08 (8%): a $1,000 booking would earn $80 instead of $75.
        """
        if value is None or value == "":
            return None
        return to_rate(value)

    @field_validator("rate")
    @classmethod
    def _check_rate(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        if value < 0 or value > 1:
            raise ValueError("rate must be between 0 and 1 (e.g. 0.08 for 8%)")
        return value

    @model_validator(mode="after")
    def _flag_unquantified_benefit(self) -> "Promotion":
        """A promotion with no measured benefit is allowed but never trusted.

        This is the normal state for a rule captured as raw marketing text
        whose terms have not been parsed yet. It is forced to "unknown" so the
        eligibility validator keeps it out of reported savings.
        """
        if self.rate is None and self.fixed_amount is None:
            # object.__setattr__ avoids re-triggering validate_assignment.
            object.__setattr__(self, "requires_verification", True)
            object.__setattr__(self, "verification_status", "unknown")
        return self

    @property
    def is_expired(self) -> bool:
        if self.valid_until is None:
            return False
        return self.valid_until < date.today()

    def matches_platform(self, platform: str) -> bool:
        if self.platform.strip() in {"*", ""}:
            return True
        return self.platform.strip().lower() == platform.strip().lower()
