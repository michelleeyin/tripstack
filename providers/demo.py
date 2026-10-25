"""Deterministic demo provider.

Prices are generated from local fixtures in ``data/demo_hotels.json`` and are
clearly labelled ``data_mode="demo"``. They are reproducible for demos and
tests, and must never be presented as live quotes.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..config import DATA_DIR, get_settings
from ..models.hotel import HotelOffer
from ..models.money import to_money
from .base import HotelProvider

DEFAULT_FIXTURES = DATA_DIR / "demo_hotels.json"

# Deterministic per-platform multiplier band, indexed by a stable hash.
_SPREAD = [
    Decimal("1.00"),
    Decimal("1.06"),
    Decimal("0.94"),
    Decimal("1.12"),
    Decimal("0.88"),
]

TAX_RATE = Decimal("0.125")
RESORT_FEE_PER_STAY = Decimal("25.00")


class DemoProvider(HotelProvider):
    """Reproducible fixture-backed provider used by Demo Mode."""

    name = "DemoProvider"
    mode = "demo"

    def __init__(self, fixtures_path: Path | None = None, seed: int | None = None) -> None:
        self.fixtures_path = Path(fixtures_path or DEFAULT_FIXTURES)
        self.seed = seed if seed is not None else get_settings().demo_seed
        self._fixtures: list[dict] | None = None

    def load_fixtures(self) -> list[dict]:
        if self._fixtures is None:
            if not self.fixtures_path.exists():
                raise FileNotFoundError(
                    f"Demo fixtures not found at {self.fixtures_path}"
                )
            with self.fixtures_path.open(encoding="utf-8") as fh:
                self._fixtures = json.load(fh)
        return self._fixtures

    async def search_hotels(
        self,
        city: str,
        check_in: date,
        check_out: date,
        adults: int = 1,
        limit: int = 20,
    ) -> list[HotelOffer]:
        nights = (check_out - check_in).days
        if nights <= 0:
            raise ValueError("check_out must be after check_in")

        settings = get_settings()
        retrieved_at = datetime.now()
        offers: list[HotelOffer] = []

        for hotel in self.load_fixtures():
            if hotel["city"].strip().lower() != city.strip().lower():
                continue
            for idx, (platform, cfg) in enumerate(hotel["platforms"].items()):
                nightly = self._jitter(
                    Decimal(str(cfg["nightly"])), hotel["hotel_id"], platform, nights
                )
                base = to_money(nightly * nights)
                taxes = to_money(base * TAX_RATE)
                fees = RESORT_FEE_PER_STAY if cfg.get("resort_fee", True) else Decimal("0.00")
                offers.append(
                    HotelOffer(
                        offer_id=f"{hotel['hotel_id']}-{_slug(platform)}-{idx}",
                        hotel_id=hotel["hotel_id"],
                        hotel_name=hotel["hotel_name"],
                        city=hotel["city"],
                        check_in=check_in,
                        check_out=check_out,
                        room_type=cfg.get("room_type", "Standard"),
                        platform=platform,
                        currency=hotel.get("currency", "USD"),
                        base_price=base,
                        taxes=taxes,
                        mandatory_fees=fees,
                        refundable=bool(cfg.get("refundable", True)),
                        cancellation_policy=cfg.get(
                            "cancellation_policy",
                            "Free cancellation until 48h before check-in"
                            if cfg.get("refundable", True)
                            else "Non-refundable",
                        ),
                        source_url=cfg.get(
                            "source_url", "https://example.com/demo-offer"
                        ),
                        data_mode="demo",
                        retrieved_at=retrieved_at,
                    )
                )

        offers.sort(key=lambda o: o.base_price)
        return offers[:limit] if limit else offers

    def _jitter(
        self, nightly: Decimal, hotel_id: str, platform: str, nights: int
    ) -> Decimal:
        """Stable pseudo-variation so each platform quotes a different price."""
        digest = hashlib.sha256(
            f"{self.seed}|{hotel_id}|{platform}|{nights}".encode()
        ).hexdigest()
        idx = int(digest[:8], 16) % len(_SPREAD)
        return to_money(nightly * _SPREAD[idx])


def _slug(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())
