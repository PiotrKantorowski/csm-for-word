#!/usr/bin/env python3
"""Evaluate CSM pseudonymization against the mapping grid corpus.

The evaluator intentionally uses the plain-text redactor path. It is a fast local
release gate for detector quality and reversibility; it does not replace the
Windows/Word/OOXML/manual GUI gates.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from redactor import _pl_placeholder_family, collect_ambiguous_person_warnings, make_replacements  # noqa: E402

DEFAULT_CASES = ROOT / "server" / "data" / "regression_cases" / "pseudonymization_mapping_grid_cases.json"


def _restore_plain_text(masked: str, replacements: list[Any]) -> str:
    restored = masked
    for rep in sorted(replacements, key=lambda r: len(r.placeholder), reverse=True):
        restored = restored.replace(rep.placeholder, rep.original)
    return restored


def _case_stats_template() -> dict[str, int]:
    return {
        "PASS": 0,
        "FAIL_FALSE_NEGATIVE": 0,
        "FAIL_FALSE_POSITIVE": 0,
        "FAIL_WRONG_CATEGORY": 0,
        "RESTORE_FAIL": 0,
        "AMBIGUOUS_WARNING": 0,
    }


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    text = case["text"]
    masked, replacements = make_replacements(text)
    cats = [r.category for r in replacements]
    originals = [r.original for r in replacements]
    restored = _restore_plain_text(masked, replacements)
    warnings = collect_ambiguous_person_warnings(replacements)

    failures: list[dict[str, str]] = []

    for value in case.get("expect_masked", []):
        if value in masked:
            failures.append({"type": "FAIL_FALSE_NEGATIVE", "value": value})
        if not any(value == original or value in original or original in value for original in originals):
            failures.append({"type": "FAIL_FALSE_NEGATIVE", "value": value, "detail": "not present in replacement originals"})

    for value in case.get("expect_unmasked", []):
        if value not in masked:
            failures.append({"type": "FAIL_FALSE_POSITIVE", "value": value})

    # Category expectations are compared at the placeholder-family level, which
    # is what the user actually sees in the document (COMPANY and CONTRACTOR
    # both render as [FIRMA_n]). Exact category matches still pass unchanged.
    families = {_pl_placeholder_family(c) for c in cats}
    for category in case.get("expected_categories", []):
        if category not in cats and _pl_placeholder_family(category) not in families:
            failures.append({"type": "FAIL_WRONG_CATEGORY", "value": category, "detail": "expected category missing"})

    for category in case.get("not_expected_categories", []):
        if category in cats or _pl_placeholder_family(category) in families:
            failures.append({"type": "FAIL_FALSE_POSITIVE", "value": category, "detail": "forbidden category present"})

    if restored != text:
        failures.append({"type": "RESTORE_FAIL", "value": case.get("id", "<unknown>")})

    return {
        "id": case.get("id"),
        "category": case.get("category", "UNCATEGORIZED"),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "masked": masked,
        "replacements": [asdict(r) for r in replacements],
        "restored_equals_input": restored == text,
    }


def evaluate(cases_path: Path) -> dict[str, Any]:
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in cases]
    by_category: dict[str, dict[str, int]] = defaultdict(_case_stats_template)
    totals = _case_stats_template()

    for result in results:
        category = result["category"] or "UNCATEGORIZED"
        if result["warnings"]:
            by_category[category]["AMBIGUOUS_WARNING"] += len(result["warnings"])
            totals["AMBIGUOUS_WARNING"] += len(result["warnings"])
        if not result["failures"]:
            by_category[category]["PASS"] += 1
            totals["PASS"] += 1
            continue
        seen_failure_types = {f["type"] for f in result["failures"]}
        for failure_type in seen_failure_types:
            by_category[category][failure_type] += 1
            totals[failure_type] += 1

    return {
        "cases_path": str(cases_path),
        "case_count": len(cases),
        "totals": totals,
        "by_category": dict(sorted(by_category.items())),
        "results": results,
    }


def print_text_report(report: dict[str, Any]) -> None:
    print(f"Cases: {report['case_count']}")
    print("Totals:")
    for key, value in report["totals"].items():
        print(f"  {key}: {value}")
    print("\nCoverage by category:")
    for category, stats in report["by_category"].items():
        stat_line = ", ".join(f"{k}: {v}" for k, v in stats.items())
        print(f"  Category: {category} | {stat_line}")
    failing = [r for r in report["results"] if r["failures"]]
    if failing:
        print("\nFailures:")
        for result in failing:
            print(f"  - {result['id']} ({result['category']}):")
            for failure in result["failures"]:
                detail = f" — {failure.get('detail')}" if failure.get("detail") else ""
                print(f"      {failure['type']}: {failure['value']}{detail}")


def _force_utf8_output() -> None:
    """Print Polish legal text regardless of the console code page.

    The report contains Polish characters. On a Windows console or pipe that
    defaults to a non-Polish ANSI code page (cp1252 on English systems and on CI
    runners) writing them raises UnicodeEncodeError and the evaluator exits 1
    without having found any real defect.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Evaluate CSM pseudonymization mapping grid corpus")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="Path to JSON case corpus")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON report")
    parser.add_argument("--fail-on-errors", action="store_true", help="Exit 1 if any failure bucket is non-zero")
    args = parser.parse_args(argv)

    report = evaluate(args.cases)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_text_report(report)

    fail_total = sum(v for k, v in report["totals"].items() if k.startswith("FAIL") or k == "RESTORE_FAIL")
    if args.fail_on_errors and fail_total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
