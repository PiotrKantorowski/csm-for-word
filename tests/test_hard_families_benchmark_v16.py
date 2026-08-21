"""Guards the v1.6 hard-families benchmark (OCR damage, merged/glued text,
flattened tables, bare ambiguous surnames, address without an anchor label,
checksum-vs-context disambiguation robustness).

Unlike the default mapping grid, this corpus intentionally contains cases the
engine is known NOT to handle yet (see docs/dev-reports/CSM_V16_HARD_FAMILIES_BENCHMARK_REPORT.md).
The test pins the exact set of currently-failing case ids so that:
- a regression on any currently-passing case (a real accuracy loss) fails the suite;
- an unplanned fix of a currently-known gap also fails the suite, forcing this
  test (and the report) to be updated deliberately instead of drifting silently.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "server" / "data" / "regression_cases" / "pseudonymization_hard_families_v16.json"

KNOWN_GAP_IDS = {
    "A1_ocr_pesel_spaces",
    "B1_merged_words_name",
    "D1_bare_ambiguous_surname",
    "E2_address_no_anchor_label",
}


def _run_evaluator() -> dict:
    proc = subprocess.run(
        [sys.executable, "tools/evaluate_pseudonymization_grid.py", "--cases", str(CASES_PATH), "--json"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


def test_hard_families_case_count_and_ids_are_stable():
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    assert len(cases) == 10
    assert KNOWN_GAP_IDS <= {c["id"] for c in cases}


def test_hard_families_no_new_false_positives_or_restore_failures():
    report = _run_evaluator()
    assert report["totals"]["FAIL_FALSE_POSITIVE"] == 0
    assert report["totals"]["RESTORE_FAIL"] == 0


def test_hard_families_known_gaps_are_exactly_pinned():
    report = _run_evaluator()
    all_ids = {r["id"] for r in report["results"]}
    failing_ids = {r["id"] for r in report["results"] if r["failures"]}

    assert failing_ids == KNOWN_GAP_IDS, (
        "The set of failing hard-family cases changed. If a case now passes, that is "
        "good news — update docs/dev-reports/CSM_V16_HARD_FAMILIES_BENCHMARK_REPORT.md and KNOWN_GAP_IDS "
        "deliberately. If a previously-passing case now fails, that is a real regression."
    )
    assert all_ids - failing_ids == all_ids - KNOWN_GAP_IDS
