"""RC33 public business/legal corpus hardening.

This benchmark intentionally excludes court judgments and blank forms. It is
based on public contract-register, administrative-decision, public-procurement
contract and public-aid document structures, with synthetic or public-source-
derived identifiers. It contains no client documents.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redactor import _restore_text_value, make_replacements

FIXTURE = Path(__file__).parent / "fixtures" / "public_business_legal_corpus_benchmark_rc33.json"
DATA = json.loads(FIXTURE.read_text(encoding="utf-8"))
CASES = DATA["cases"]


def _run_case(text: str):
    masked, replacements = make_replacements(text)
    restored, report = _restore_text_value(masked, [r.__dict__ for r in replacements])
    assert report["all_found"], report
    assert restored == text
    return masked, replacements


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_rc33_public_business_legal_case(case):
    masked, replacements = _run_case(case["input"])
    for fragment in case.get("must_mask", []):
        assert fragment not in masked, f"{case['id']} leaked {fragment!r}: {masked!r}"
    for fragment in case.get("must_keep", []):
        assert fragment in masked, f"{case['id']} removed expected text {fragment!r}: {masked!r}"
    originals = {r.original for r in replacements}
    for fragment in case.get("must_not_create", []):
        assert fragment not in originals, f"{case['id']} created unwanted replacement for {fragment!r}: {originals!r}"


def test_rc33_public_business_corpus_scope():
    assert len(CASES) >= 30
    assert "court judgments" in DATA["excluded_sources"]
    assert "blank court/administrative forms" in DATA["excluded_sources"]
    profiles = {case["profile"] for case in CASES}
    assert {"contract_register", "administrative_decision", "procurement_contract", "public_aid", "b2b_contract", "false_positive"} <= profiles
    assert DATA["sources"]["brpo_contract_register"]["url"]
    assert DATA["sources"]["uodo_decision_portal"]["url"]
    assert DATA["sources"]["sudop_public_aid_search"]["url"]
