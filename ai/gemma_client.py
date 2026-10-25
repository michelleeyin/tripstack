"""Observable, bounded Ollama inference with explicit failure diagnostics."""
from __future__ import annotations

import json
import time
from typing import Any

import httpx

from ..config import get_settings
from .prompts import build_prompt

__all__ = ['GemmaClient', 'GemmaUnavailable']


class GemmaUnavailable(RuntimeError):
    """Transport, model loading or structured-output failure."""


class GemmaClient:
    def __init__(self, host=None, model=None, timeout_s=None, *, cpu=False, transport=None):
        settings = get_settings()
        self.host = (host or settings.ollama_host).rstrip('/')
        self.model = model or settings.ollama_model
        self.timeout_s = timeout_s or settings.ollama_timeout_s
        self.cpu = cpu
        self.transport = transport
        self.last_metrics: dict[str, Any] = {}

    def _client(self, timeout=None):
        return httpx.Client(timeout=timeout or self.timeout_s, transport=self.transport, trust_env=False)

    def diagnostics(self) -> dict[str, Any]:
        """Model installed does NOT mean model inference has passed."""
        result = {'reachable': False, 'installed': False, 'models': [], 'model': self.model,
                  'message': '', 'inference_verified': False}
        try:
            with self._client(min(self.timeout_s, 5)) as client:
                response = client.get(f'{self.host}/api/tags')
                response.raise_for_status()
                names = [m['name'] for m in response.json().get('models', [])]
            result.update(reachable=True, models=names, installed=self.model in names)
            result['message'] = ('Model installed; run the inference check.' if result['installed']
                                 else f'Model not installed: {self.model}')
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            result['message'] = f'Ollama connection failed: {exc}'
        return result

    def is_available(self):
        return self.diagnostics()['installed']

    def generate_json(self, prompt: str) -> dict[str, Any]:
        # A schema prevents extra keys and unbounded prose; Pydantic still validates
        # the returned values, and the parser separately grounds them in source text.
        from .promotion_parser import ExtractionDraft
        payload = {'model': self.model, 'prompt': prompt, 'stream': False,
                   'format': ExtractionDraft.model_json_schema(), 'keep_alive': '5m',
                   'options': {'temperature': 0, 'num_ctx': 4096, 'num_predict': 512}}
        if self.cpu:
            payload['options']['num_gpu'] = 0
        start = time.perf_counter()
        self.last_metrics = {}
        try:
            with self._client() as client:
                response = client.post(f'{self.host}/api/generate', json=payload)
                if response.is_error:
                    try:
                        detail = response.json().get('error', response.text)
                    except ValueError:
                        detail = response.text
                    raise GemmaUnavailable(f'Ollama HTTP {response.status_code}: {str(detail)[:1200]}')
                body = response.json()
            if body.get('error'):
                raise GemmaUnavailable(str(body['error']))
            if body.get('done_reason') == 'length':
                raise GemmaUnavailable('Model output reached the token limit; result rejected.')
            data = _extract_json(body.get('response', ''))
            if not isinstance(data, dict):
                raise GemmaUnavailable('Model did not return a JSON object')
            self.last_metrics = {
                'elapsed_ms': round((time.perf_counter() - start) * 1000),
                'prompt_tokens': body.get('prompt_eval_count', 0),
                'output_tokens': body.get('eval_count', 0),
                'load_ms': round(body.get('load_duration', 0) / 1_000_000),
                'inference_verified': True,
            }
            return data
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise GemmaUnavailable(f'Ollama request failed: {exc}') from exc
        finally:
            self.last_metrics.setdefault('elapsed_ms', round((time.perf_counter() - start) * 1000))


def _extract_json(raw: str) -> Any:
    raw = raw.strip()
    if raw.startswith('```'):
        raw = raw.strip('`').removeprefix('json').strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find('{'), raw.rfind('}')
        if start < 0 or end <= start:
            raise GemmaUnavailable('No JSON object found in model output')
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError as exc:
            raise GemmaUnavailable(f'Malformed JSON from model: {exc}') from exc


def build_extraction_prompt(terms: str) -> str:
    return build_prompt(terms)
