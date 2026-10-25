"""Hotel offer schema — the normalized shape every provider must return."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .money import to_money


class HotelOffer(BaseModel):
    """A single bookable room offer on a single platform."""

    model_config = ConfigDict(validate_assignment=True)

    offer_id: str
    hotel_id: str
    hotel_name: str
    city: str
    check_in: date
    check_out: date
    room_type: str = "Standard"
    platform: str
    currency: str = "USD"
    base_price: Decimal
    taxes: Decimal = Field(default=Decimal("0.00"))
    mandatory_fees: Decimal = Field(default=Decimal("0.00"))
    refundable: bool = True
    cancellation_policy: str = "Unknown"
    source_url: str = ""
    data_mode: Literal["live", "demo", "fixture"] = "demo"
    retrieved_at: datetime | None = None

    @field_validator("base_price", "taxes", "mandatory_fees", mode="before")
    @classmethod
    def _coerce_money(cls, value: object) -> Decimal:
        return to_money(value)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def _validate_stay(self) -> "HotelOffer":
        if self.check_out <= self.check_in:
            raise ValueError(
                f"check_out ({self.check_out}) must be after check_in ({self.check_in})"
            )
        if self.base_price < 0:
            raise ValueError("base_price cannot be negative")
        return self

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def taxes_and_fees(self) -> Decimal:
        return to_money(self.taxes + self.mandatory_fees)

    @property
    def is_simulated(self) -> bool:
        """True when the price did not come from a live provider call."""
        return self.data_mode in {"demo", "fixture"}

    @property
    def segment_key(self) -> str:
        return f"{self.city.lower()}|{self.check_in.isoformat()}|{self.check_out.isoformat()}"


class TripSegment(BaseModel):
    """One lodging leg of a trip (one city, one date range)."""

    city: str
    check_in: date
    check_out: date

    @model_validator(mode="after")
    def _validate_dates(self) -> "TripSegment":
        if self.check_out <= self.check_in:
            raise ValueError(
                f"{self.city}: check_out must be after check_in"
            )
        return self

    @property
    def nights(self) -> int:
        return (self.check_out - self.check_in).days

    @property
    def key(self) -> str:
        return f"{self.city.lower()}|{self.check_in.isoformat()}|{self.check_out.isoformat()}"


class TripRequest(BaseModel):
    """User-supplied trip definition."""

    currency: str = "USD"
    budget: Decimal = Decimal("0.00")
    travelers: int = 1
    segments: list[TripSegment]
    refundable_only: bool = False
    include_estimated_cashback: bool = True
    objective: Literal["lowest_net", "lowest_upfront", "lowest_certain"] = "lowest_net"

    @field_validator("budget", mode="before")
    @classmethod
    def _coerce_budget(cls, value: object) -> Decimal:
        return to_money(value)

    @field_validator("currency")
    @classmethod
    def _upper_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("travelers")
    @classmethod
    def _check_travelers(cls, value: int) -> int:
        if value < 1:
            raise ValueError("travelers must be >= 1")
        return value

    @model_validator(mode="after")
    def _validate_segments(self) -> "TripRequest":
        if not self.segments:
            raise ValueError("a trip needs at least one segment")
        for i in range(1, len(self.segments)):
            prev, cur = self.segments[i - 1], self.segments[i]
            if cur.check_in < prev.check_out:
                raise ValueError(
                    f"segment '{cur.city}' starts before '{prev.city}' ends; "
                    "MVP assumes fixed, non-overlapping dates"
                )
        return self

    @property
    def total_nights(self) -> int:
        return sum(s.nights for s in self.segments)
