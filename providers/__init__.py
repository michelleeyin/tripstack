"""Hotel providers: demo fixtures and (optional) Amadeus live search."""

from .amadeus import AmadeusProvider
from .base import HotelProvider, ProviderError, search_sync
from .demo import DemoProvider

__all__ = [
    "HotelProvider",
    "ProviderError",
    "DemoProvider",
    "AmadeusProvider",
    "search_sync",
]


def get_provider(mode: str | None = None):
    """Return a provider for ``mode`` ("live" | "demo").

    Falls back to the demo provider when live credentials are absent, so the
    app never silently claims live pricing it cannot deliver.
    """
    from ..config import get_settings

    settings = get_settings()
    requested = (mode or settings.effective_mode).lower()
    if requested == "live" and settings.live_ready:
        return AmadeusProvider()
    return DemoProvider()
