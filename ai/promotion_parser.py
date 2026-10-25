"""Natural-language promotion parsing (Gemma via Ollama + safe fallback).

Parsed fields are validated before pricing. Unresolved conditions are marked
``requires_verification`` and excluded from reported savings.
"""

from __future__ import annotations

import re
import time
import math
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from ..config import get_settings
from ..models.money import to_money, to_rate
from ..models.promotion import Promotion
from .gemma_client import GemmaClient, GemmaUnavailable
from .prompts import build_prompt

__all__ = [
    "ExtractionDraft",
    "ParseTrace",
    "parse_promotion_terms",
    "heuristic_extract",
    "enrich_promotions",
]


class ExtractionDraft(BaseModel):
    """Schema the model output must satisfy before it is trusted."""

    model_config = ConfigDict(extra="ignore")

    promotion_type: str | None = None
    rate: float | None = None
    fixed_amount: float | None = None
    cap: float | None = None
    minimum_spend: float | None = None
    taxes_eligible: bool | None = None
    stackable: bool | None = None
    valid_until: str | None = None
    requires_verification: bool | None = None
    notes: str | None = None

    @field_validator("fixed_amount", "cap", "minimum_spend")
    @classmethod
    def _money_range(cls, value):
        if value is not None and (not math.isfinite(value) or value < 0):
            raise ValueError("Amounts must be finite and non-negative")
        return value

    @field_validator("rate")
    @classmethod
    def _rate_range(cls, value: float | None) -> float | None:
        if value is None:
            return None
        # Accept "8" meaning 8% as well as "0.08".
        if value > 1:
            value = value / 100
        if not math.isfinite(value) or value < 0 or value > 1:
            raise ValueError("rate out of range")
        return value


@dataclass
class ParseTrace:
    """Explainability record: how a promotion was derived."""

    promotion_id: str
    method: str = "heuristic"  # "gemma" | "heuristic" | "hybrid" | "failed"
    model: str = ""
    raw_output: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    metrics: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    fallback_reason: str = ""


NUMERIC_FIELDS = ("rate", "fixed_amount", "cap", "minimum_spend")
SEMANTIC_FIELDS = (
    "promotion_type",
    "taxes_eligible",
    "stackable",
    "valid_until",
    "requires_verification",
)


def parse_promotion_terms(
    terms: str,
    promotion_id: str,
    platform: str = "*",
    source_url: str = "",
    use_ai: bool = True,
    client: GemmaClient | None = None,
    strategy: str = "ai",
) -> tuple[Promotion, ParseTrace]:
    """Turn free-text promotion terms into a validated :class:`Promotion`.

    Strategies:
      * ``"ai"``     — Gemma first, rule-based fallback if it fails.
      * ``"rules"``  — deterministic parser only.
      * ``"hybrid"`` — numbers come from the deterministic parser (they are
        grounded in the text by construction), semantics come from Gemma,
        which reads phrasing the regexes cannot. Measured results are in
        ``docs/parser-benchmark.md``.

    Never raises on bad model output.
    """
    started = time.perf_counter()
    trace = ParseTrace(promotion_id=promotion_id)
    draft: ExtractionDraft | None = None

    use_ai = use_ai and get_settings().use_ai_parser and strategy in {"ai", "hybrid"}
    if use_ai:
        try:
            gemma = client or GemmaClient()
            raw = gemma.generate_json(build_prompt(terms))
            draft = ExtractionDraft.model_validate(raw)
            trace.model = gemma.model
            trace.raw_output = raw
            trace.metrics = dict(getattr(gemma, "last_metrics", {}))
        except (GemmaUnavailable, ValidationError, ValueError) as exc:
            trace.fallback_reason = str(exc)
            trace.warnings.append(f"AI extraction unavailable or invalid: {exc}")
            draft = None

    rule_draft = ExtractionDraft.model_validate(heuristic_extract(terms))

    if strategy == "hybrid" and draft is not None:
        merged = _merge_drafts(draft, rule_draft, trace)
        trace.method = "hybrid"
        promo = _draft_to_promotion(
            merged, promotion_id, platform, source_url, terms, trace
        )
        _finish_trace(promo, trace, terms, started)
        return promo, trace

    if draft is None:
        draft = rule_draft
        if trace.method != "gemma":
            trace.method = "heuristic"
            trace.raw_output = dict(rule_draft)
            trace.warnings.append(
                "Parsed with rule-based fallback; verify terms before relying "
                "on this promotion"
            )
    else:
        trace.method = "gemma"

    promo = _draft_to_promotion(draft, promotion_id, platform, source_url, terms, trace)
    _finish_trace(promo, trace, terms, started)
    return promo, trace


def _finish_trace(promo, trace, terms, started):
    trace.elapsed_ms = round((time.perf_counter() - started) * 1000)
    for key in NUMERIC_FIELDS:
        value = getattr(promo, key)
        if value is None:
            continue
        pattern = _PCT_RE if key == "rate" else _MONEY_RE
        target = float(value * 100) if key == "rate" else float(value)
        for match in pattern.finditer(terms):
            if abs(float(match.group(1).replace(",", "")) - target) < 0.00001:
                trace.evidence[key] = terms[max(0, match.start()-40):min(len(terms), match.end()+60)]
                break
    for key, words in {"stackable": r"combin|stack|coupon", "taxes_eligible": r"tax|fee",
                       "valid_until": r"valid|expir|through|until"}.items():
        for sentence in re.split(r"(?<=[.!?])\s+|\n", terms):
            if re.search(words, sentence, re.IGNORECASE):
                trace.evidence[key] = sentence
                break


def _merge_drafts(
    ai: ExtractionDraft, rules: ExtractionDraft, trace: ParseTrace
) -> ExtractionDraft:
    """Numbers from rules, meaning from the model, conflicts flagged.

    Numeric fields come from the rule parser *only*. Every value it produces is
    copied from source matches. When the rules find nothing, the field stays
    null rather than accepting a model number.
    Measured: letting model numbers fill the gaps cost ~3 points of accuracy
    (see docs/parser-benchmark.md), typically by reusing a figure that belongs
    to a different field.
    """
    merged = ai.model_dump()
    for field in NUMERIC_FIELDS:
        rule_value = getattr(rules, field)
        ai_value = getattr(ai, field)
        if ai_value is not None and (
            rule_value is None
            or round(float(ai_value), 4) != round(float(rule_value), 4)
        ):
            trace.warnings.append(
                f"Model returned {field}={ai_value}; using the rule-parser value "
                f"{rule_value} instead (grounded in the source text)"
            )
        merged[field] = rule_value

    for field in SEMANTIC_FIELDS:
        value = getattr(ai, field)
        rule_value = getattr(rules, field)
        if field in {"stackable", "taxes_eligible"} and rule_value is not None:
            if value is not None and value != rule_value:
                trace.warnings.append(f"Explicit source condition overrides model {field}={value}")
            value = rule_value
        elif value is None:
            value = rule_value
        merged[field] = value

    merged["notes"] = f"hybrid: {ai.notes or 'no model note'}"
    return ExtractionDraft.model_validate(merged)


def _ground_numbers(
    draft: ExtractionDraft, terms: str, trace: ParseTrace
) -> ExtractionDraft:
    """Drop any number the model produced that does not appear in the source.

    Measured behaviour: small models copy figures from the prompt examples or
    invent plausible ones. A value that cannot be found in the promotional
    text is discarded and flagged, so a hallucinated rate can never reach the
    pricing engine.
    """
    percentages = {round(float(m), 4) for m in _PCT_RE.findall(terms or "")}
    amounts = {
        round(float(m.replace(",", "")), 2) for m in _MONEY_RE.findall(terms or "")
    }

    if draft.rate is not None and round(draft.rate * 100, 4) not in percentages:
        trace.warnings.append(
            f"Model returned rate {draft.rate}, which does not appear in the "
            "source text; value discarded"
        )
        object.__setattr__(draft, "rate", None)

    for field in ("fixed_amount", "cap", "minimum_spend"):
        value = getattr(draft, field)
        if value is not None and round(float(value), 2) not in amounts:
            trace.warnings.append(
                f"Model returned {field}={value}, which does not appear in the "
                "source text; value discarded"
            )
            object.__setattr__(draft, field, None)

    # A hallucinated expiry date is the most dangerous of all: 2023-04-01 was
    # invented for promotions with no date, which would silently mark a valid
    # offer as expired (or keep an expired one alive).
    if draft.valid_until and not _date_appears(draft.valid_until, terms):
        trace.warnings.append(
            f"Model returned valid_until={draft.valid_until}, which does not "
            "appear in the source text; value discarded"
        )
        object.__setattr__(draft, "valid_until", None)

    return draft


def _date_appears(value: str, terms: str) -> bool:
    """True when the date literally occurs in the promotional text."""
    value = value.strip()
    if value and value in terms:
        return True
    parsed = _parse_date(value)
    if parsed is None:
        return False
    candidates = {
        parsed.isoformat(),
        parsed.strftime("%m/%d/%Y"),
        parsed.strftime("%-m/%-d/%Y"),
        parsed.strftime("%Y/%m/%d"),
    }
    return any(c in terms for c in candidates)


def _draft_to_promotion(
    draft: ExtractionDraft,
    promotion_id: str,
    platform: str,
    source_url: str,
    terms: str,
    trace: ParseTrace,
) -> Promotion:
    draft = _ground_numbers(draft, terms, trace)
    ptype = (draft.promotion_type or "cashback").lower()
    if ptype not in {"cashback", "instant_discount", "coupon"}:
        trace.warnings.append(f"Unknown promotion_type '{ptype}'; treated as cashback")
        ptype = "cashback"

    source_fields = heuristic_extract(terms)
    role_conflict = False
    for key in ("fixed_amount", "cap", "minimum_spend"):
        source_value = source_fields[key]
        model_value = getattr(draft, key)
        if source_value is not None and (model_value is None or abs(source_value - model_value) > .005):
            role_conflict = True
            trace.warnings.append(f"{key} conflicts with its source role; review required")

    valid_until = _parse_date(draft.valid_until)

    rate = to_rate(draft.rate) if draft.rate is not None else None
    fixed = to_money(draft.fixed_amount) if draft.fixed_amount is not None else None
    if rate is None and fixed is None:
        # Nothing usable was extracted — never invent a benefit.
        trace.method = "failed"
        trace.warnings.append(
            "No benefit could be extracted; promotion marked as requiring "
            "verification and excluded from savings"
        )
        fixed = Decimal("0.00")
        ptype = "cashback"

    # Positive semantics cannot override explicit source exclusions in AI mode either.
    rules = heuristic_extract(terms)
    for key in ("stackable", "taxes_eligible"):
        if rules[key] is not None and getattr(draft, key) != rules[key]:
            trace.warnings.append(f"Explicit source condition used for {key}")
            object.__setattr__(draft, key, rules[key])
    from .prompts import MAX_TERMS_CHARS
    ambiguous = len(set(_PCT_RE.findall(terms))) > 1 or len(terms) > MAX_TERMS_CHARS
    if ambiguous:
        trace.warnings.append("Multiple rates or truncated terms require manual review; excluded from savings")
    needs_check = bool(draft.requires_verification) or trace.method == "failed" or ambiguous or role_conflict

    return Promotion(
        promotion_id=promotion_id,
        platform=platform,
        type=ptype,  # type: ignore[arg-type]
        rate=rate,
        fixed_amount=fixed,
        cap=to_money(draft.cap) if draft.cap is not None else None,
        minimum_spend=(
            to_money(draft.minimum_spend) if draft.minimum_spend is not None else None
        ),
        taxes_eligible=bool(draft.taxes_eligible),
        stackable=bool(draft.stackable),
        valid_until=valid_until,
        source_url=source_url,
        raw_text=terms,
        verification_status="unknown" if needs_check else "estimated",
        requires_verification=needs_check,
        notes=draft.notes or "",
    )


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m-%d-%Y"):
        try:
            from datetime import datetime

            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------
# Deterministic fallback parser
# --------------------------------------------------------------------------

_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_AMOUNT_PATTERN = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?(?![\d,]|\.\d)"
_MONEY_RE = re.compile(r"\$\s?(" + _AMOUNT_PATTERN + r")")
_CAP_RE = re.compile(
    r"(?:maximum|max|up to|capped at|cap(?:ped)? (?:at|of)?)\D{0,20}\$\s?(" + _AMOUNT_PATTERN + r")",
    re.IGNORECASE,
)
_MIN_RE = re.compile(
    r"(?:minimum|min\.?(?:\s*purchase)?|at least|spend|purchase|orders? of|of)"
    r"\D{0,15}\$\s?(" + _AMOUNT_PATTERN + r")"
    r"(?:\s*(?:or more|or above|\+|and up|and above))?",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})")


def heuristic_extract(terms: str) -> dict[str, Any]:
    """Rule-based extraction used when the model is unavailable.

    Conservative by design: unrecognised fields stay ``None``.
    """
    text = terms or ""
    low = text.lower()

    rate: float | None = None
    pct = _PCT_RE.search(text)
    if pct:
        rate = float(pct.group(1)) / 100

    moneys = [float(m.replace(",", "")) for m in _MONEY_RE.findall(text)]
    fixed: float | None = None
    cap_match = _CAP_RE.search(text)
    cap = float(cap_match.group(1).replace(",", "")) if cap_match else None
    min_match = _MIN_RE.search(text)
    minimum = float(min_match.group(1).replace(",", "")) if min_match else None

    # A money value that is neither the cap nor the minimum is treated as a
    # fixed discount, but only when no percentage was found.
    for value in moneys:
        if cap is not None and abs(value - cap) < 0.005:
            continue
        if minimum is not None and abs(value - minimum) < 0.005:
            continue
        if rate is None and fixed is None:
            fixed = value
        break

    # Classify from the FIRST SENTENCE only. Later clauses such as "cannot be
    # combined with cashback offers" mention cashback without describing this
    # promotion, which previously mislabelled instant discounts.
    ptype = "cashback"
    head = re.split(r"(?<=[.!?])\s+", text.strip())[0].lower() if text.strip() else ""

    if re.search(r"\b(coupon|promo(?:tion)? code|use code|code)\b", head):
        ptype = "coupon"
    elif re.search(
        r"\b(cash ?back|statement credit|rewards|earn|receive)\b"
        r"|\d+(?:\.\d+)?\s*%\s*(?:cash ?back|back)\b",
        head,
    ):
        ptype = "cashback"
    elif re.search(r"\b(instant|save|off|discount)\b", head):
        ptype = "instant_discount"
    elif re.search(r"\b(cash ?back|rewards|earn)\b", low):
        ptype = "cashback"

    stackable = None
    if re.search(r"(not valid with|cannot be combin|not combin|excludes .* coupon|no stacking)", low):
        stackable = False
    elif re.search(r"(can be combin|stackable|combinable)", low):
        stackable = True

    taxes_eligible = None
    if re.search(r"(taxes and fees are excluded|excludes taxes|excluding taxes|excl.*tax)", low):
        taxes_eligible = False
    elif re.search(r"(including taxes|taxes are eligible)", low):
        taxes_eligible = True

    date_match = _DATE_RE.search(text)
    ambiguous = bool(rate is None and fixed is None)

    return {
        "promotion_type": ptype,
        "rate": rate,
        "fixed_amount": fixed,
        "cap": cap,
        "minimum_spend": minimum,
        "taxes_eligible": taxes_eligible,
        "stackable": stackable,
        "valid_until": date_match.group(1) if date_match else None,
        "requires_verification": ambiguous,
        "notes": "Rule-based extraction; confirm the original terms.",
    }


def enrich_promotions(
    promotions: list[Promotion],
    use_ai: bool = True,
    client: GemmaClient | None = None,
    strategy: str = "ai",
) -> tuple[list[Promotion], list[ParseTrace]]:
    """Re-extract promotions that ship only raw marketing text.

    Curated rules (already structured) are returned untouched.
    """
    traces: list[ParseTrace] = []
    out: list[Promotion] = []
    for promo in promotions:
        if not promo.raw_text or (promo.rate is not None or promo.fixed_amount is not None):
            out.append(promo)
            continue
        parsed, trace = parse_promotion_terms(
            promo.raw_text,
            promo.promotion_id,
            platform=promo.platform,
            source_url=promo.source_url,
            use_ai=use_ai,
            client=client,
            strategy=strategy,
        )
        traces.append(trace)
        out.append(parsed)
    return out, traces
