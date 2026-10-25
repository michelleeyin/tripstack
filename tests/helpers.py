"""Shared test fixtures."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from tripstack.models.hotel import HotelOffer, TripRequest, TripSegment
from tripstack.models.promotion import Promotion

TODAY = date(2026, 10, 24)
RETRIEVED = datetime(2026, 10, 24, 18, 0, 0)


def offer(
    offer_id: str = "demo-001",
    platform: str = "Provider A",
    city: str = "Chicago",
    base: str = "850.00",
    taxes: str = "100.00",
    fees: str = "25.00",
    refundable: bool = True,
    currency: str = "USD",
    hotel_name: str = "Example Hotel",
) -> HotelOffer:
    return HotelOffer(
        offer_id=offer_id,
        hotel_id=f"hotel-{offer_id}",
        hotel_name=hotel_name,
        city=city,
        check_in=date(2026, 11, 10),
        check_out=date(2026, 11, 15),
        room_type="Standard King",
        platform=platform,
        currency=currency,
        base_price=Decimal(base),
        taxes=Decimal(taxes),
        mandatory_fees=Decimal(fees),
        refundable=refundable,
        source_url="https://example.com",
        data_mode="demo",
        retrieved_at=RETRIEVED,
    )


def cashback(
    promo_id: str = "promo-001",
    platform: str = "Provider A",
    rate: str | None = "0.08",
    cap: str | None = "30.00",
    minimum_spend: str | None = "100.00",
    taxes_eligible: bool = False,
    stackable: bool = False,
    valid_until: date | None = date(2026, 12, 31),
    status: str = "estimated",
    fixed: str | None = None,
) -> Promotion:
    return Promotion(
        promotion_id=promo_id,
        platform=platform,
        type="cashback",
        rate=Decimal(rate) if rate else None,
        fixed_amount=Decimal(fixed) if fixed else None,
        cap=Decimal(cap) if cap else None,
        minimum_spend=Decimal(minimum_spend) if minimum_spend else None,
        taxes_eligible=taxes_eligible,
        stackable=stackable,
        valid_until=valid_until,
        source_url="https://example.com/promo",
        verification_status=status,
    )


def instant(
    promo_id: str = "promo-instant",
    platform: str = "Provider A",
    fixed: str = "25.00",
    minimum_spend: str | None = "200.00",
    stackable: bool = False,
    status: str = "estimated",
) -> Promotion:
    return Promotion(
        promotion_id=promo_id,
        platform=platform,
        type="instant_discount",
        fixed_amount=Decimal(fixed),
        minimum_spend=Decimal(minimum_spend) if minimum_spend else None,
        stackable=stackable,
        valid_until=date(2026, 12, 31),
        source_url="https://example.com/promo",
        verification_status=status,
    )


def trip_request(
    budget: str = "2500.00",
    objective: str = "lowest_net",
    refundable_only: bool = False,
    cities: tuple[str, ...] = ("Chicago",),
) -> TripRequest:
    segments = []
    start = date(2026, 11, 10)
    for city in cities:
        segments.append(
            TripSegment(city=city, check_in=start, check_out=start.replace(day=start.day + 5))
        )
        start = start.replace(day=start.day + 5)
    return TripRequest(
        currency="USD",
        budget=Decimal(budget),
        travelers=2,
        segments=segments,
        refundable_only=refundable_only,
        objective=objective,
    )
