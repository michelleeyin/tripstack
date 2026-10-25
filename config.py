"""TripStack configuration.

Secrets are read from environment variables only (see ``.env.example``).
Nothing here should ever be committed with real credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPO_ROOT = BASE_DIR.parent


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    """Runtime settings. ``data_mode`` is "demo" unless live keys exist."""

    data_mode: str
    amadeus_client_id: str
    amadeus_client_secret: str
    amadeus_host: str
    ollama_host: str
    ollama_model: str
    ollama_timeout_s: float
    use_ai_parser: bool
    http_timeout_s: float
    demo_seed: int

    @property
    def live_ready(self) -> bool:
        return bool(self.amadeus_client_id and self.amadeus_client_secret)

    @property
    def effective_mode(self) -> str:
        """Live mode is only advertised when credentials are actually present."""
        return "live" if (self.data_mode == "live" and self.live_ready) else "demo"


def get_settings() -> Settings:
    return Settings(
        data_mode=os.getenv("TRIPSTACK_DATA_MODE", "demo").strip().lower(),
        amadeus_client_id=os.getenv("AMADEUS_CLIENT_ID", ""),
        amadeus_client_secret=os.getenv("AMADEUS_CLIENT_SECRET", ""),
        amadeus_host=os.getenv(
            "AMADEUS_HOST", "test.api.amadeus.com"
        ).strip(),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").strip(),
        ollama_model=os.getenv("OLLAMA_MODEL", "gemma:2b").strip(),
        ollama_timeout_s=_env_float("OLLAMA_TIMEOUT_S", 25.0),
        use_ai_parser=_env_bool("TRIPSTACK_USE_AI_PARSER", True),
        http_timeout_s=_env_float("TRIPSTACK_HTTP_TIMEOUT_S", 20.0),
        demo_seed=int(os.getenv("TRIPSTACK_DEMO_SEED", "7")),
    )
