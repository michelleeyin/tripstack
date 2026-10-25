"""Provider contract.

Every provider returns :class:`HotelOffer` objects so the engine never needs
to know where a price came from. Providers must record ``data_mode`` and
``retrieved_at`` so the UI can always disclose provenance.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from ..models.hotel import HotelOffer


class ProviderError(RuntimeError):
    """Raised for transport, auth, quota and empty-result failures."""


class HotelProvider(ABC):
    """Abstract hotel search provider."""

    name: str = "base"
    mode: str = "demo"  # "live" | "demo"

    @abstractmethod
    async def search_hotels(
        self,
        city: str,
        check_in: date,
        check_out: date,
        adults: int = 1,
        limit: int = 20,
    ) -> list[HotelOffer]:
        """Return normalized offers for one city and date range."""

    def describe(self) -> str:
        return f"{self.name} ({self.mode} mode)"


def search_sync(
    provider: HotelProvider,
    city: str,
    check_in: date,
    check_out: date,
    adults: int = 1,
    limit: int = 20,
) -> list[HotelOffer]:
    """Run an async provider from synchronous UI code (Streamlit)."""
    import asyncio

    return asyncio.run(
        provider.search_hotels(city, check_in, check_out, adults=adults, limit=limit)
    )
