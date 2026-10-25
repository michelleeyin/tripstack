"""Loaders for the local JSON data sets (demo trip, promotion rules)."""

from __future__ import annotations

import json
from pathlib import Path

from .config import DATA_DIR
from .models.hotel import TripRequest
from .models.promotion import Promotion

__all__ = ["load_demo_trip", "load_promotions", "load_raw_promotions"]


def load_demo_trip(path: Path | None = None) -> TripRequest:
    path = Path(path or DATA_DIR / "demo_trip.json")
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    return TripRequest.model_validate(
        {
            "currency": payload.get("currency", "USD"),
            "budget": payload.get("budget", 0),
            "travelers": payload.get("travelers", 1),
            "segments": payload["segments"],
            "refundable_only": payload.get("refundable_only", False),
            "objective": payload.get("objective", "lowest_net"),
        }
    )


def load_raw_promotions(path: Path | None = None) -> tuple[list[Promotion], str]:
    """Return promotions plus the data-set disclaimer text."""
    path = Path(path or DATA_DIR / "promotion_rules.json")
    with path.open(encoding="utf-8") as fh:
        payload = json.load(fh)
    promos = [Promotion.model_validate(p) for p in payload.get("promotions", [])]
    return promos, payload.get("disclaimer", "")


def load_promotions(path: Path | None = None) -> list[Promotion]:
    promos, _ = load_raw_promotions(path)
    return promos
