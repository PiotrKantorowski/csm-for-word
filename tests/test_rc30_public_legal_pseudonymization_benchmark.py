"""Public-source-derived legal pseudonymization benchmark for CSM.

The fixture is built from public legal-form structures (Gov.pl, Senate and court
BIP templates) plus synthetic PII inserted into those structures. It does not
contain client documents or confidential legal material.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redactor import _restore_text_value, make_replacements

FIXTURE = Path(__file__).parent / "fixtures" / "public_legal_pseudonymization_benchmark.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = DATA["cases"]


def _run_case(text: str):
    masked, replacements = make_replacements(text)
    restored, report = _restore_text_value(masked, [r.__dict__ for r in replacements])
    assert report["all_found"], report
    assert restored == text
    return masked, replacements


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_public_legal_benchmark_case(case):
    masked, replacements = _run_case(case["input"])
    for fragment in case.get("must_mask", []):
        assert fragment not in masked, f"{case['id']} leaked {fragment!r}: {masked!r}"
    for fragment in case.get("must_keep", []):
        assert fragment in masked, f"{case['id']} removed expected text {fragment!r}: {masked!r}"


def test_public_legal_benchmark_has_minimum_scope():
    assert len(CASES) >= 100
    profiles = {case["profile"] for case in CASES}
    assert {"contracts", "pleadings", "power_of_attorney", "false_positive"} <= profiles
    assert DATA["sources"]["gov_vehicle_sale_pdf"]
