from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from redactor import make_replacements


def test_legal_document_title_is_not_masked_as_company():
    masked, replacements = make_replacements("UMOWA SPRZEDAŻY\nPOSTANOWIENIA KOŃCOWE")
    assert masked == "UMOWA SPRZEDAŻY\nPOSTANOWIENIA KOŃCOWE"
    assert not any(r.category in {"COMPANY", "CONTRACTOR", "COMPANY_ALIAS"} for r in replacements)


def test_party_company_without_suffix_still_masks():
    masked, replacements = make_replacements("Powód: OLIMP LABORATORIES wnosi pozew.")
    assert "OLIMP LABORATORIES" not in masked
    assert any(r.category == "CONTRACTOR" and r.original == "OLIMP LABORATORIES" for r in replacements)


def test_mapping_grid_evaluator_default_corpus_passes():
    proc = subprocess.run(
        [sys.executable, "tools/evaluate_pseudonymization_grid.py", "--json", "--fail-on-errors"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["totals"]["FAIL_FALSE_NEGATIVE"] == 0
    assert report["totals"]["FAIL_FALSE_POSITIVE"] == 0
    assert report["totals"]["FAIL_WRONG_CATEGORY"] == 0
    assert report["totals"]["RESTORE_FAIL"] == 0


def test_case_ref_masks_complete_dotted_identifier_without_sentence_tail():
    text = "nr sprawy ABC.123.4.2026. Kolejny akapit pozostaje jawny."
    masked, replacements = make_replacements(text)
    assert "ABC.123.4.2026" not in masked
    assert "Kolejny akapit pozostaje jawny" in masked
    assert any(r.category == "CASE_REF" and r.original == "ABC.123.4.2026" for r in replacements)


def test_url_masking_preserves_following_comma():
    text = "Kontakt: https://panel.example.pl, example.pl."
    masked, replacements = make_replacements(text)
    assert "https://panel.example.pl" not in masked
    assert "," in masked
    assert any(r.category == "URL" and r.original == "https://panel.example.pl" for r in replacements)


def test_birth_date_and_short_vehicle_registration_contexts_are_masked():
    text = "IP 192.168.1.1, data urodzenia 1 stycznia 1980 r., nr rej. RZE 12345."
    masked, replacements = make_replacements(text)
    assert "192.168.1.1" not in masked
    assert "1 stycznia 1980 r" not in masked
    assert "RZE 12345" not in masked
    assert any(r.category == "BIRTH_DATA" and r.original == "1 stycznia 1980 r" for r in replacements)
    assert any(r.category == "VEHICLE_ID" and r.original == "RZE 12345" for r in replacements)
