"""Amadeus hotel provider (Live Mode).

Requires ``AMADEUS_CLIENT_ID`` / ``AMADEUS_CLIENT_SECRET``. Access, coverage
and permitted usage of the Amadeus Self-Service APIs must be verified before
using this in production; the test host only returns sandbox data.

Flow:
  1. OAuth2 client-credentials token
  2. /v1/reference-data/locations/hotels/by-city  -> hotelIds for the city
  3. /v3/shopping/hotel-offers                    -> prices for those hotels
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import httpx

from ..engine.location import provider_coordinates
from ..config import get_settings
from ..models.hotel import HotelOffer
from ..models.money import to_money
from .base import HotelProvider, ProviderError

# Amadeus needs an IATA city code. Common demo cities are mapped; anything
# else is resolved through the locations endpoint.
CITY_CODES = {
    "chicago": "CHI",
    "new york": "NYC",
    "boston": "BOS",
    "san francisco": "SFO",
    "los angeles": "LAX",
    "seattle": "SEA",
    "washington": "WAS",
    "miami": "MIA",
    "austin": "AUS",
    "denver": "DEN",
}


class AmadeusProvider(HotelProvider):
    name = "AmadeusProvider"
    mode = "live"

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        host: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        settings = get_settings()
        self.client_id = client_id or settings.amadeus_client_id
        self.client_secret = client_secret or settings.amadeus_client_secret
        self.host = (host or settings.amadeus_host).strip()
        self.timeout_s = timeout_s or settings.http_timeout_s
        self._token: str | None = None
        self._hotel_coordinates: dict[str, tuple] = {}

    # -- auth ------------------------------------------------------------
    def _get_token(self) -> str:
        if self._token:
            return self._token
        if not (self.client_id and self.client_secret):
            raise ProviderError(
                "Amadeus credentials missing. Set AMADEUS_CLIENT_ID and "
                "AMADEUS_CLIENT_SECRET, or run in Demo Mode."
            )
        url = f"https://{self.host}/v1/security/oauth2/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(url, data=data)
                resp.raise_for_status()
                self._token = resp.json()["access_token"]
        except Exception as exc:  # noqa: BLE001 - surfaced as ProviderError
            raise ProviderError(f"Amadeus auth failed: {exc}") from exc
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}"}

    # -- search ----------------------------------------------------------
    async def search_hotels(
        self,
        city: str,
        check_in: date,
        check_out: date,
        adults: int = 1,
        limit: int = 20,
    ) -> list[HotelOffer]:
        if (check_out - check_in).days <= 0:
            raise ValueError("check_out must be after check_in")

        city_code = await self._resolve_city_code(city)
        hotel_ids = await self._hotel_ids_for_city(city_code, limit)
        if not hotel_ids:
            raise ProviderError(
                f"No hotels returned by Amadeus for '{city}' ({city_code})"
            )
        return await self._fetch_offers(
            hotel_ids, city, check_in, check_out, adults, limit
        )

    async def _resolve_city_code(self, city: str) -> str:
        key = city.strip().lower()
        if key in CITY_CODES:
            return CITY_CODES[key]
        url = f"https://{self.host}/v1/reference-data/locations"
        params = {"keyword": city, "subType": "CITY", "page[limit]": 1}
        data = await self._get(url, params)
        items = data.get("data") or []
        if not items:
            raise ProviderError(f"Could not resolve an IATA city code for '{city}'")
        return items[0]["iataCode"]

    async def _hotel_ids_for_city(self, city_code: str, limit: int) -> list[str]:
        url = f"https://{self.host}/v1/reference-data/locations/hotels/by-city"
        params = {"cityCode": city_code, "radius": 20, "radiusUnit": "KM"}
        data = await self._get(url, params)
        for hotel in data.get("data", []):
            geo = hotel.get("geoCode") or {}
            self._hotel_coordinates[hotel.get("hotelId", "")] = provider_coordinates(
                geo.get("latitude"), geo.get("longitude"))
        ids = [h.get("hotelId") for h in data.get("data", []) if h.get("hotelId")]
        return ids[: max(5, min(limit, 40))]

    async def _fetch_offers(
        self,
        hotel_ids: list[str],
        city: str,
        check_in: date,
        check_out: date,
        adults: int,
        limit: int,
    ) -> list[HotelOffer]:
        url = f"https://{self.host}/v3/shopping/hotel-offers"
        params = {
            "hotelIds": ",".join(hotel_ids),
            "adults": adults,
            "checkInDate": check_in.isoformat(),
            "checkOutDate": check_out.isoformat(),
            "bestRateOnly": "true",
        }
        data = await self._get(url, params)
        offers: list[HotelOffer] = []
        retrieved_at = datetime.now()

        for hotel in data.get("data", []):
            hotel_info = hotel.get("hotel", {})
            hotel_id = hotel_info.get("hotelId", "unknown")
            hotel_name = hotel_info.get("name", "Unknown hotel")
            coordinates = provider_coordinates(hotel_info.get("latitude"), hotel_info.get("longitude"))
            if coordinates[0] is None:
                coordinates = self._hotel_coordinates.get(hotel_id, (None, None))
            for offer in hotel.get("offers", []):
                normalized = _normalize_offer(
                    hotel_id, hotel_name, city, offer, check_in, check_out, retrieved_at,
                    latitude=coordinates[0], longitude=coordinates[1],
                )
                if normalized is not None:
                    offers.append(normalized)
            if len(offers) >= limit:
                break

        if not offers:
            raise ProviderError(
                "Amadeus returned no priced offers for the requested dates"
            )
        return offers[:limit]

    async def _get(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.get(url, params=params, headers=self._headers())
                resp.raise_for_status()
                return resp.json()
        except ProviderError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(f"Amadeus request failed: {exc}") from exc


def _normalize_offer(
    hotel_id: str,
    hotel_name: str,
    city: str,
    offer: dict[str, Any],
    check_in: date,
    check_out: date,
    retrieved_at: datetime,
    latitude: float | None = None,
    longitude: float | None = None,
) -> HotelOffer | None:
    """Map one Amadeus offer onto the shared schema.

    Amadeus reports ``total`` (incl. taxes) and sometimes a ``base``. When
    taxes are not itemised we derive them as total - base and never invent
    a tax figure.
    """
    price = offer.get("price") or {}
    currency = (price.get("currency") or "USD").upper()
    total = price.get("total")
    if total is None:
        return None
    base = price.get("base")
    base_value = to_money(base if base is not None else total)
    total_value = to_money(total)
    taxes = to_money(total_value - base_value)
    # Per-stay charges that Amadeus lists as not included in the total are
    # surfaced as mandatory fees rather than silently folded into the price.
    mandatory_fees = to_money(
        sum(
            Decimal(str(t.get("amount") or 0))
            for t in (price.get("taxes") or [])
            if t.get("included") is False
            and (t.get("pricingFrequency") or "").upper() == "PER_STAY"
        )
    )
    refundable = _is_refundable(offer)
    latitude, longitude = provider_coordinates(latitude, longitude)
    return HotelOffer(
        offer_id=f"amadeus-{hotel_id}-{offer.get('id', '0')}",
        hotel_id=hotel_id,
        hotel_name=hotel_name,
        city=city,
        latitude=latitude,
        longitude=longitude,
        location_source="provider" if latitude is not None else "unknown",
        check_in=check_in,
        check_out=check_out,
        room_type=(offer.get("room") or {}).get("typeEstimated", {}).get("category")
        or (offer.get("room") or {}).get("type")
        or "Standard",
        platform="Amadeus",
        currency=currency,
        base_price=base_value,
        taxes=taxes if taxes > 0 else Decimal("0.00"),
        mandatory_fees=mandatory_fees,
        refundable=refundable,
        cancellation_policy=_policy_text(offer),
        source_url="https://developers.amadeus.com/self-service/category/hotels",
        data_mode="live",
        retrieved_at=retrieved_at,
    )


def _is_refundable(offer: dict[str, Any]) -> bool:
    # Penalty amounts/types describe what is charged, not a refund promise.
    # The boolean schema cannot express unknown/conditional refundability;
    # only an explicit unconditional refund flag passes refundable-only filters.
    policies = offer.get("policies") or {}
    refund = policies.get("refundable") or {}
    if not isinstance(refund, dict):
        return False
    status = str(refund.get("cancellationRefund", "")).upper()
    if status:
        return status == "REFUNDABLE"
    # The v3 cancellation array contains penalties. Only explicitly zero
    # penalties across all periods establish free cancellation without needing
    # deadline inference. Missing amounts and FULL_STAY remain unconfirmed.
    cancellations = policies.get("cancellations") or []
    if not cancellations:
        return False
    for penalty in cancellations:
        if str(penalty.get("type", "")).upper() == "FULL_STAY":
            return False
        amount = penalty.get("amount")
        if amount is None:
            return False
        try:
            value = Decimal(str(amount))
            if not value.is_finite() or value != 0:
                return False
        except (ValueError, ArithmeticError):
            return False
    return True


def _policy_text(offer: dict[str, Any]) -> str:
    policies = offer.get("policies") or {}
    cancellations = policies.get("cancellations") or []
    if not cancellations:
        return "Cancellation policy not provided by provider"
    first = cancellations[0]
    deadline = first.get("deadline") or "unknown"
    return f"Cancellation deadline: {deadline}"
