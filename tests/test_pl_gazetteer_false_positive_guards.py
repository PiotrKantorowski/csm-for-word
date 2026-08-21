"""
Tests that PII detection does NOT produce false positives in Polish text.

Verifies:
- Common nouns that double as surnames are not masked without context
- Generic document section labels are not masked
- Lowercase locality names are not masked
- Court-like phrases without explicit court type are not masked
- Strings from the hard-negative lists are never masked
- Restore roundtrip produces exact original for all cases

Each test is a negative test: the expectation is NO finding (or no finding of
a specific category).
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
# Helper
# ---------------------------------------------------------------------------

def _make_ooxml(text: str) -> str:
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


def assert_no_pii_and_restore(text: str, forbidden_categories=("PERSON", "COMPANY", "CONTRACTOR")) -> None:
    findings = collect_findings(text)
    bad = [f for f in findings if f.category in forbidden_categories]
    assert not bad, (
        f"False positive: {text!r} produced unexpected {forbidden_categories} findings: {bad}"
    )
    # Restore roundtrip (even if no findings, the text must survive mask→restore intact)
    ooxml = _make_ooxml(text)
    masked_xml, replacements = mask_ooxml(ooxml)
    restored_xml = restore_ooxml(masked_xml, [r.__dict__ for r in replacements])
    restored_text = re.sub(r"<[^>]+>", "", restored_xml)
    assert restored_text == text, (
        f"Restore roundtrip failed:\n  input:    {text!r}\n  restored: {restored_text!r}"
    )


# ---------------------------------------------------------------------------
# Common nouns that are also surnames — no context → no PERSON
# ---------------------------------------------------------------------------

def test_mucha_lowercase_no_person():
    """'mucha' in sentence context is a common noun (fly), not a surname."""
    assert_no_pii_and_restore("Na stole siedzial mucha.")


def test_mucha_sentence_no_person():
    assert_no_pii_and_restore("Na stole siedzIala mucha.")


def test_lis_no_person():
    """'lis' = fox; alone without title prefix must not be masked."""
    assert_no_pii_and_restore("Lis biegal po lesie.")


def test_wilk_no_person():
    """'wilk' = wolf."""
    assert_no_pii_and_restore("Wilk zjadl owce.")


def test_kot_no_person():
    """'kot' = cat."""
    assert_no_pii_and_restore("Kot siedzial na macie.")


def test_pustynia_lowercase_no_address():
    """Lowercase 'pustynia' (desert) in sentence context — not a place reference."""
    findings = collect_findings("Na pustyni bylo goraco.")
    address_findings = [f for f in findings if "ADDRESS" in f.category]
    assert not address_findings, f"False positive ADDRESS: {address_findings}"


def test_pustynia_as_paragraph_heading_no_address():
    """'Pustynia' as standalone capitalized word (e.g., chapter title) must not be masked."""
    # Without address context it should not be masked
    findings = collect_findings("Pustynia")
    address_findings = [f for f in findings if "ADDRESS" in f.category]
    assert not address_findings, f"False positive ADDRESS: {address_findings}"


# ---------------------------------------------------------------------------
# Generic document labels from pl_legal_labels_negative.json
# ---------------------------------------------------------------------------

HARD_NEGATIVE_LABELS = [
    "Dane Klienta",
    "Dane Strony",
    "Dane Kontrahenta",
    "Nazwa Spolki",
    "Adres Siedziby",
    "Numer Umowy",
    "Data Umowy",
    "Postanowienia Koncowe",
    "Warunki Platnosci",
    "Przedmiot Umowy",
    "Strony Umowy",
    "Dane Osobowe",
    "Osoba Kontaktowa",
    "Forma Prawna",
]


@pytest.mark.parametrize("label", HARD_NEGATIVE_LABELS)
def test_generic_label_not_masked(label):
    """Hard-negative labels must never be detected as PERSON or COMPANY."""
    assert_no_pii_and_restore(label)


def test_block_of_labels_unchanged():
    """A block of form labels must remain completely unmasked."""
    block = "\n".join([
        "Dane Klienta",
        "Nazwa Spolki",
        "Adres Siedziby",
        "Numer Umowy",
        "Data Umowy",
    ])
    findings = collect_findings(block)
    bad = [f for f in findings if f.category in ("PERSON", "COMPANY", "CONTRACTOR")]
    assert not bad, f"False positive in label block: {bad}"


def test_labels_and_real_data_only_masks_data():
    """When labels appear next to real data, only the data is masked."""
    text = "Dane Klienta: Jan Kowalski\nNazwa Spolki: NUTRIFARM sp. z o.o."
    findings = collect_findings(text)
    # 'Jan Kowalski' should be PERSON
    person_findings = [f for f in findings if f.category == "PERSON"]
    assert person_findings, "Expected Jan Kowalski to be masked"
    # 'NUTRIFARM sp. z o.o.' should be COMPANY
    company_findings = [f for f in findings if f.category == "COMPANY"]
    assert company_findings, "Expected NUTRIFARM to be masked"
    # But labels themselves must not be in findings
    all_values = {f.value for f in findings}
    assert "Dane Klienta" not in all_values
    assert "Nazwa Spolki" not in all_values


# ---------------------------------------------------------------------------
# Document headings / ALL CAPS — no masking without legal form
# ---------------------------------------------------------------------------

UPPERCASE_HEADINGS = [
    "UMOWA SPRZEDAZY",
    "WEZWANIE DO ZAPLATY",
    "OSTATECZNE PRZEDSADOWE",
    "POZEW O ZAPLATE",
    "UCHWALA NR 1",
    "ZALACZNIK NR 1",
    "FAKTURA VAT",
]


@pytest.mark.parametrize("heading", UPPERCASE_HEADINGS)
def test_document_heading_not_company(heading):
    """All-caps document headings must not be detected as COMPANY."""
    findings = collect_findings(heading)
    bad = [f for f in findings if f.category in ("COMPANY", "CONTRACTOR")]
    assert not bad, f"False positive COMPANY for heading {heading!r}: {bad}"


# ---------------------------------------------------------------------------
# Court-like phrases — only full court names with type qualifier trigger COURT
# ---------------------------------------------------------------------------

def test_sad_stwierdzi_no_court():
    """Bare 'Sąd' without type qualifier (Rejonowy/Okręgowy/etc.) is not COURT."""
    findings = collect_findings("Sad stwierdzil, ze umowa jest wazna.")
    court_findings = [f for f in findings if f.category == "COURT"]
    assert not court_findings, f"False positive COURT: {court_findings}"


def test_sad_nakazal_no_court():
    findings = collect_findings("Sad nakazal zaplacic odsetki.")
    court_findings = [f for f in findings if f.category == "COURT"]
    assert not court_findings, f"False positive COURT: {court_findings}"


# ---------------------------------------------------------------------------
# Generic label stoplist in gazetteer pipeline
# ---------------------------------------------------------------------------

def test_generic_label_not_in_gazetteer_findings():
    """Gazetteer pipeline must not produce findings for generic labels."""
    sys.path.insert(0, str(ROOT / "server"))
    from redactor import collect_gazetteer_findings
    for label in ["Dane Klienta", "Nazwa Spolki", "Adres Siedziby"]:
        findings = collect_gazetteer_findings(label)
        assert not findings, (
            f"collect_gazetteer_findings returned findings for label {label!r}: {findings}"
        )


# ---------------------------------------------------------------------------
# Restore roundtrip for all negative cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Na stole siedzial mucha.",
    "Lis biegal po lesie.",
    "Wilk zjadl owce.",
    "Na pustyni bylo goraco.",
    "Sad stwierdzil, ze...",
    "UMOWA SPRZEDAZY",
    "FAKTURA VAT",
    "Dane Klienta",
    "Nazwa Spolki",
    "Adres Siedziby",
    "Postanowienia Koncowe",
])
def test_negative_cases_restore_roundtrip(text):
    """Even for texts with no PII, mask→restore must produce exact original."""
    ooxml = _make_ooxml(text)
    masked_xml, replacements = mask_ooxml(ooxml)
    restored_xml = restore_ooxml(masked_xml, [r.__dict__ for r in replacements])
    restored_text = re.sub(r"<[^>]+>", "", restored_xml)
    assert restored_text == text, (
        f"Restore roundtrip failed for non-PII text:\n  input:    {text!r}\n  restored: {restored_text!r}"
    )
