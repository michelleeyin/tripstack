"""Benchmark: Gemma (Ollama) vs. the rule-based promotion parser.

    python benchmark_parser.py            # runs both parsers over the labelled set
    python benchmark_parser.py --no-ai    # rule-based only
    python benchmark_parser.py --save     # also write docs/parser-benchmark.md

Scoring is field-level against hand-written ground truth in
``data/promotion_bench.json``. A field scores 1 when the parser reproduces the
label (money/rate within 0.005), otherwise 0. ``requires_verification`` is
scored as a safety flag: for the ambiguous case the parser must raise it.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from tripstack.ai.gemma_client import GemmaClient
from tripstack.ai.promotion_parser import parse_promotion_terms
from tripstack.config import DATA_DIR, get_settings
from tripstack.models.promotion import Promotion

BENCH_PATH = DATA_DIR / "promotion_bench.json"
DOCS_PATH = Path(__file__).resolve().parent / "docs" / "parser-benchmark.md"

MONEY_FIELDS = ("rate", "fixed_amount", "cap", "minimum_spend")
BOOL_FIELDS = ("taxes_eligible", "stackable", "requires_verification")
TOL = Decimal("0.005")


def score_case(promo: Promotion, expected: dict) -> dict[str, int]:
    scores: dict[str, int] = {}

    scores["type"] = int(promo.type == expected["type"])

    for field in MONEY_FIELDS:
        got = getattr(promo, field)
        want = expected[field]
        if want is None:
            scores[field] = int(got is None)
        elif got is None:
            scores[field] = 0
        else:
            scores[field] = int(abs(Decimal(str(got)) - Decimal(str(want))) <= TOL)

    for field in BOOL_FIELDS:
        scores[field] = int(bool(getattr(promo, field)) == bool(expected[field]))

    want_date = expected.get("valid_until")
    got_date = promo.valid_until
    if want_date is None:
        scores["valid_until"] = int(got_date is None)
    else:
        scores["valid_until"] = int(
            got_date is not None
            and got_date.isoformat() == date.fromisoformat(want_date).isoformat()
        )

    return scores


def run(use_ai: bool = True) -> dict:
    cases = json.loads(BENCH_PATH.read_text(encoding="utf-8"))["cases"]
    settings = get_settings()
    gemma = GemmaClient()
    model_available = gemma.is_available() if use_ai else False

    rows = []
    for case in cases:
        text = case["text"]
        expected = case["expected"]

        promo_ai, trace = parse_promotion_terms(
            text, f"bench-{case['id']}", platform="*", use_ai=use_ai and model_available
        )
        promo_rule, _ = parse_promotion_terms(
            text, f"bench-{case['id']}-rule", platform="*", use_ai=False
        )
        promo_hybrid, hybrid_trace = parse_promotion_terms(
            text,
            f"bench-{case['id']}-hybrid",
            platform="*",
            use_ai=use_ai and model_available,
            strategy="hybrid",
        )

        rows.append(
            {
                "id": case["id"],
                "text": text,
                "method": trace.method,
                "model": trace.model or settings.ollama_model,
                "ai_scores": score_case(promo_ai, expected),
                "rule_scores": score_case(promo_rule, expected),
                "hybrid_scores": score_case(promo_hybrid, expected),
                "ai_promo": _short(promo_ai),
                "rule_promo": _short(promo_rule),
                "hybrid_promo": _short(promo_hybrid),
                "expected": expected,
            }
        )

    fields = ["type"] + list(MONEY_FIELDS) + list(BOOL_FIELDS) + ["valid_until"]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "model": settings.ollama_model,
        "ollama_reachable": model_available,
        "cases": len(rows),
        "fields": fields,
        "ai_totals": {f: sum(r["ai_scores"][f] for r in rows) for f in fields},
        "rule_totals": {f: sum(r["rule_scores"][f] for r in rows) for f in fields},
        "hybrid_totals": {f: sum(r["hybrid_scores"][f] for r in rows) for f in fields},
        "ai_called": sum(1 for r in rows if r["method"] == "gemma"),
        "rows": rows,
    }
    total_possible = len(rows) * len(fields)

    def _acc(key: str) -> float:
        return round(sum(summary[key].values()) / total_possible, 4)

    def _case_acc(key: str) -> float:
        scores = "ai_scores" if key == "ai_totals" else (
            "rule_scores" if key == "rule_totals" else "hybrid_scores"
        )
        return round(sum(1 for r in rows if all(r[scores].values())) / len(rows), 4)

    summary["ai_accuracy"] = _acc("ai_totals")
    summary["rule_accuracy"] = _acc("rule_totals")
    summary["hybrid_accuracy"] = _acc("hybrid_totals")
    summary["ai_case_accuracy"] = _case_acc("ai_totals")
    summary["rule_case_accuracy"] = _case_acc("rule_totals")
    summary["hybrid_case_accuracy"] = _case_acc("hybrid_totals")
    return summary


def _short(promo: Promotion) -> dict:
    return {
        "type": promo.type,
        "rate": float(promo.rate) if promo.rate is not None else None,
        "fixed_amount": float(promo.fixed_amount) if promo.fixed_amount is not None else None,
        "cap": float(promo.cap) if promo.cap is not None else None,
        "minimum_spend": float(promo.minimum_spend) if promo.minimum_spend is not None else None,
        "taxes_eligible": promo.taxes_eligible,
        "stackable": promo.stackable,
        "valid_until": promo.valid_until.isoformat() if promo.valid_until else None,
        "requires_verification": promo.requires_verification,
    }


def render_markdown(summary: dict) -> str:
    fields = summary["fields"]
    n = summary["cases"]
    lines = [
        "# Promotion parser benchmark — Gemma vs. rule-based fallback",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Model: `{summary['model']}` served by Ollama "
        f"(reachable: {summary['ollama_reachable']})",
        f"- Cases: {n} labelled texts × {len(fields)} fields",
        f"- AI parser actually invoked: {summary['ai_called']}/{n} "
        "(the rest fell back to rules)",
        "",
        "## Headline",
        "",
        "| Metric | Gemma | Rule-based | Hybrid |",
        "|---|---|---|---|",
        f"| Field-level accuracy | {summary['ai_accuracy']:.1%} | "
        f"{summary['rule_accuracy']:.1%} | {summary['hybrid_accuracy']:.1%} |",
        f"| Perfect cases (all {len(fields)} fields) | "
        f"{summary['ai_case_accuracy']:.1%} | {summary['rule_case_accuracy']:.1%} | "
        f"{summary['hybrid_case_accuracy']:.1%} |",
        "",
        "*Hybrid* = numeric fields from the rule parser (grounded in the text), "
        "semantic fields from Gemma.",
        "",
        "## Per-field correct counts",
        "",
        "| Field | Gemma | Rule-based | Hybrid |",
        "|---|---|---|---|",
    ]
    for f in fields:
        lines.append(
            f"| `{f}` | {summary['ai_totals'][f]}/{n} | "
            f"{summary['rule_totals'][f]}/{n} | {summary['hybrid_totals'][f]}/{n} |"
        )

    lines += [
        "",
        "## Per-case detail",
        "",
        "| Case | Gemma | Rules | Hybrid | Hybrid misses |",
        "|---|---|---|---|---|",
    ]
    for row in summary["rows"]:
        hy_miss = [f for f, v in row["hybrid_scores"].items() if not v]
        lines.append(
            f"| {row['id']} | {sum(row['ai_scores'].values())}/{len(fields)} "
            f"| {sum(row['rule_scores'].values())}/{len(fields)} "
            f"| {sum(row['hybrid_scores'].values())}/{len(fields)} "
            f"| {', '.join(hy_miss) or '—'} |"
        )

    lines += [
        "",
        "## Notes",
        "",
        "- Ground truth is hand-labelled in `data/promotion_bench.json`.",
        "- `requires_verification` is a safety flag: case c08 is deliberately "
        "ambiguous and must be flagged rather than guessed.",
        "- A money/rate field is correct when within 0.005 of the label.",
        "- Neither parser's output reaches the pricing engine unvalidated; "
        "everything passes through Pydantic first.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-ai", action="store_true", help="skip the model entirely")
    parser.add_argument("--save", action="store_true", help="write docs/parser-benchmark.md")
    parser.add_argument("--json", action="store_true", help="print raw JSON")
    args = parser.parse_args()

    summary = run(use_ai=not args.no_ai)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(render_markdown(summary))

    if args.save:
        DOCS_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOCS_PATH.write_text(render_markdown(summary), encoding="utf-8")
        print(f"\nWrote {DOCS_PATH}")


if __name__ == "__main__":
    main()
