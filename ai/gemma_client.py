"""Thin Ollama client for the Gemma open-weight model.

No API key is required: Gemma runs locally through Ollama. Everything is
fail-soft — if Ollama is not running the caller falls back to rule-based
parsing and marks the promotion as requiring verification.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from ..config import get_settings
from .prompts import build_prompt

__all__ = ["GemmaClient", "GemmaUnavailable"]


class GemmaUnavailable(RuntimeError):
    """Raised when Ollama cannot be reached or returns an unusable response."""


class GemmaClient:
    """Minimal JSON-mode client for Ollama's /api/generate endpoint."""

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        settings = get_settings()
        self.host = (host or settings.ollama_host).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout_s = timeout_s or settings.ollama_timeout_s

    def is_available(self) -> bool:
        try:
            with httpx.Client(timeout=min(self.timeout_s, 5.0)) as client:
                resp = client.get(f"{self.host}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def generate_json(self, prompt: str) -> dict[str, Any]:
        """Send ``prompt`` and return the parsed JSON object.

        Raises :class:`GemmaUnavailable` on transport failure or unparsable
        output so callers can degrade gracefully.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.0},
        }
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                resp = client.post(f"{self.host}/api/generate", json=payload)
                resp.raise_for_status()
                body = resp.json()
        except Exception as exc:  # noqa: BLE001 - any failure is a soft failure
            raise GemmaUnavailable(f"Ollama request failed: {exc}") from exc

        raw = body.get("response", "")
        data = _extract_json(raw)
        if not isinstance(data, dict):
            raise GemmaUnavailable("Model did not return a JSON object")
        return data


def _extract_json(raw: str) -> Any:
    """Pull the first JSON object out of a possibly chatty model response."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise GemmaUnavailable("No JSON object found in model output")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError as exc:
        raise GemmaUnavailable(f"Malformed JSON from model: {exc}") from exc


def build_extraction_prompt(terms: str) -> str:
    return build_prompt(terms)
