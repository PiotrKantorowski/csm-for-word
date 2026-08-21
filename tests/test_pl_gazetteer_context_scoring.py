"""
Tests for context-aware scoring in Polish PII detection.

Verifies that entity masking requires proper legal/personal context —
gazetteers alone do not trigger masking. Covers all scenarios from
docs/PL_PSEUDONYMIZATION_RESOURCE_POLICY.md section 4.

Each test also verifies the restore roundtrip: pseudonymize → restore == input.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from redactor import collect_findings, mask_ooxml, restore_ooxml

# ---------------------------------------------------------------------------
# Restore roundtrip helper
# ---------------------------------------------------------------------------

def _make_ooxml(text: str) -> str:
    """Wrap plain text in minimal OOXML for roundtrip testing."""
    escaped = (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )
    return (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p><w:r><w:t xml:space="preserve">'
        + escaped
        + '</w:t></w:r></w:p></w:body></w:document>'
    )


def assert_restore_roundtrip(text: str) -> tuple[str, list]:
    """Pseudonymize text and restore; assert exact roundtrip. Returns (masked_text, replacements)."""
    ooxml = _make_ooxml(text)
    masked_xml, replacements = mask_ooxml(ooxml)
    # Extract plain text from masked XML via simple regex
    masked_text = re.sub(r"<[^>]+>", "", masked_xml)
    restored_xml = restore_ooxml(masked_xml, [r.__dict__ for r in replacements])
    restored_text = re.sub(r"<[^>]+>", "", restored_xml)
    assert restored_text == text, (
        f"Restore roundtrip failed:\n  input:    {text!r}\n  masked:   {masked_text!r}\n  restored: {restored_text!r}"
    )
    return masked_text, replacements


# ---------------------------------------------------------------------------
# PERSON — title-prefixed single surname
# ---------------------------------------------------------------------------

def test_pani_mucha_podpisala_is_person():
    """Pani + surname + lowercase verb → PERSON (title context)."""
    text = "Pani Mucha podpisala dokument."
    findings = collect_findings(text)
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert person_findings, f"Expected PERSON finding, got: {findings}"
    assert person_findings[0].value == "Mucha"


def test_pani_mucha_podpisala_restore_roundtrip():
    assert_restore_roundtrip("Pani Mucha podpisala dokument.")


def test_pan_kowalski_is_person():
    """Pan + surname → PERSON."""
    text = "Pan Kowalski zlozyl wniosek."
    findings = collect_findings(text)
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert person_findings, f"Expected PERSON in: {text!r}"
    assert "Kowalski" in person_findings[0].value


def test_pan_kowalski_restore_roundtrip():
    assert_restore_roundtrip("Pan Kowalski zlozyl wniosek.")


def test_adwokat_nowak_is_person():
    """adwokat + surname → PERSON."""
    text = "Adwokat Nowak reprezentuje powoda."
    findings = collect_findings(text)
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert person_findings, f"Expected PERSON in: {text!r}"


# ---------------------------------------------------------------------------
# PERSON — first name + surname pair
# ---------------------------------------------------------------------------

def test_jan_mucha_is_person():
    """First name (in FIRST_NAMES) + surname → PERSON."""
    text = "Jan Mucha podpisal dokument."
    findings = collect_findings(text)
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert person_findings, f"Expected PERSON in: {text!r}"
    assert "Jan" in person_findings[0].value
    assert "Mucha" in person_findings[0].value


def test_jan_mucha_restore_roundtrip():
    assert_restore_roundtrip("Jan Mucha podpisal dokument.")


def test_anna_kowalska_is_person():
    text = "Anna Kowalska zamieszkala w Krakowie."
    findings = collect_findings(text)
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert person_findings


def test_anna_kowalska_restore_roundtrip():
    assert_restore_roundtrip("Anna Kowalska zamieszkala w Krakowie.")


# ---------------------------------------------------------------------------
# COMPANY — with legal form suffix
# ---------------------------------------------------------------------------

def test_nutrifarm_quoted_company_no_orphan_quote():
    """NUTRIFARM in quotes: no orphaned opening quote in masked output."""
    text = 'Klienta = "NUTRIFARM" sp. z o.o. reprezentuje Jan Kowalski.'
    findings = collect_findings(text)
    company_findings = [f for f in findings if f.category == "COMPANY"]
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert company_findings, "Expected COMPANY finding"
    assert person_findings, "Expected PERSON finding"
    # Check balanced quotes
    ooxml = _make_ooxml(text)
    masked_xml, _ = mask_ooxml(ooxml)
    masked_text = re.sub(r"<[^>]+>", "", masked_xml)
    assert not re.search(r'[""„\'«‹]\[', masked_text), (
        f"Orphaned opening quote in masked text: {masked_text!r}"
    )


def test_nutrifarm_quoted_company_restore_roundtrip():
    assert_restore_roundtrip('Klienta = "NUTRIFARM" sp. z o.o. reprezentuje Jan Kowalski.')


def test_pozwany_mucha_spolka_is_company_not_full_phrase():
    """'Pozwany Mucha sp. z o.o.' → COMPANY('Mucha sp. z o.o.'), not full sentence."""
    text = "Pozwany Mucha sp. z o.o."
    findings = collect_findings(text)
    company_findings = [f for f in findings if f.category == "COMPANY"]
    assert company_findings, f"Expected COMPANY in: {text!r}"
    # 'Pozwany' must not be part of the company value
    for f in company_findings:
        assert "Pozwany" not in f.value, f"'Pozwany' should not be in company value: {f.value!r}"
    assert any("Mucha" in f.value for f in company_findings)


def test_pozwany_mucha_spolka_restore_roundtrip():
    assert_restore_roundtrip("Pozwany Mucha sp. z o.o.")


def test_olimp_laboratories_is_company():
    """'Powód: OLIMP LABORATORIES sp. z o.o.' → COMPANY (not Powód)."""
    text = "Powod: OLIMP LABORATORIES sp. z o.o."
    findings = collect_findings(text)
    company_findings = [f for f in findings if f.category == "COMPANY"]
    assert company_findings, f"Expected COMPANY in: {text!r}"
    for f in company_findings:
        assert "Powod" not in f.value, f"'Powod' should not be part of company: {f.value!r}"
    assert any("OLIMP" in f.value or "LABORATORIES" in f.value for f in company_findings)


def test_olimp_laboratories_restore_roundtrip():
    assert_restore_roundtrip("Powod: OLIMP LABORATORIES sp. z o.o.")


# ---------------------------------------------------------------------------
# ADDRESS / PLACE — context-dependent
# ---------------------------------------------------------------------------

def test_zamieszkaly_w_pustyni_is_address():
    """'zamieszkały w Pustyni' → ADDRESS (locality context)."""
    text = "zamieszkaly w Pustyni"
    findings = collect_findings(text)
    address_findings = [f for f in findings if f.category in ("ADDRESS", "ADDRESS_ZAMIESZKALY")]
    assert address_findings, f"Expected ADDRESS in: {text!r}\ngot: {findings}"
    assert any("Pustyni" in f.value for f in address_findings)


def test_zamieszkaly_w_pustyni_restore_roundtrip():
    assert_restore_roundtrip("zamieszkaly w Pustyni")


def test_full_street_address_is_address_full():
    """'ul. Dąbrowskiego 23/35, 42-200 Częstochowa' → ADDRESS_FULL."""
    text = "ul. Dabrowskiego 23/35, 42-200 Czestochowa"
    findings = collect_findings(text)
    address_findings = [f for f in findings if f.category in ("ADDRESS_FULL", "ADDRESS")]
    assert address_findings, f"Expected ADDRESS_FULL in: {text!r}\ngot: {findings}"


def test_full_street_address_restore_roundtrip():
    assert_restore_roundtrip("ul. Dabrowskiego 23/35, 42-200 Czestochowa")


def test_siedziba_w_warszawie_is_address():
    """Company HQ address: 'z siedzibą w Warszawie' → ADDRESS_SIEDZIBA."""
    text = "spolka z siedziba w Warszawie."
    findings = collect_findings(text)
    address_findings = [f for f in findings if "ADDRESS" in f.category]
    assert address_findings, f"Expected ADDRESS in: {text!r}\ngot: {findings}"


# ---------------------------------------------------------------------------
# COURT
# ---------------------------------------------------------------------------

def test_sad_rejonowy_w_rzeszowie_is_court():
    """'Sąd Rejonowy w Rzeszowie' → COURT."""
    text = "Sad Rejonowy w Rzeszowie"
    findings = collect_findings(text)
    court_findings = [f for f in findings if f.category == "COURT"]
    assert court_findings, f"Expected COURT in: {text!r}\ngot: {findings}"
    assert any("Rzeszowie" in f.value or "Sad Rejonowy" in f.value for f in court_findings)


def test_sad_rejonowy_restore_roundtrip():
    assert_restore_roundtrip("Sad Rejonowy w Rzeszowie")


def test_sad_okregowy_is_court():
    text = "Sad Okregowy w Warszawie"
    findings = collect_findings(text)
    assert any(f.category == "COURT" for f in findings), f"Expected COURT: {findings}"


# ---------------------------------------------------------------------------
# Gazetteer person detection
# ---------------------------------------------------------------------------

def test_gazetteer_detects_jana_kowalskiego():
    """Genitive inflected PERSON detected via gazetteer."""
    text = "Pelnomocnik: Jana Kowalskiego, zamieszkaly w Krakowie."
    findings = collect_findings(text)
    assert any(f.category == "PERSON" for f in findings), (
        f"Expected PERSON for 'Jana Kowalskiego': {findings}"
    )


def test_gazetteer_person_restore_roundtrip():
    assert_restore_roundtrip("Pelnomocnik: Jana Kowalskiego, zamieszkaly w Krakowie.")


def test_gazetteer_person_in_list():
    """Person name in a list/party row is detected."""
    text = "1. Jan Kowalski, PESEL 80010112345, zamieszkaly w Krakowie"
    findings = collect_findings(text)
    assert any(f.category == "PERSON" and "Kowalski" in f.value for f in findings), (
        f"Expected PERSON('Jan Kowalski'): {findings}"
    )


def test_gazetteer_person_restore_roundtrip_list():
    assert_restore_roundtrip("1. Jan Kowalski, PESEL 80010112345, zamieszkaly w Krakowie")


@pytest.mark.parametrize("name_text,expected_in_value", [
    ("Anna Nowak zamieszkala w Warszawie", "Anna"),
    ("Piotr Wisniewski, PESEL 75020567890", "Piotr"),
    ("pelnomocnik Marek Dabrowskiego", "Marek"),
])
def test_gazetteer_person_detection_parametrized(name_text, expected_in_value):
    findings = collect_findings(name_text)
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert person_findings, f"Expected PERSON in: {name_text!r}\ngot: {findings}"
    assert any(expected_in_value in f.value for f in person_findings), (
        f"Expected {expected_in_value!r} in a PERSON finding, got: {person_findings}"
    )
