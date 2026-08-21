"""
rc18 regression tests — pseudonymization fixes
==============================================

Covers:
  1. Generic document-label false positives (gazetteer + contextual detectors)
  2. Unbalanced opening quote left after quoted company name masking
  3. Gazetteer positive cases (real names still detected)
  4. Restore roundtrip for the NUTRIFARM/quoted-company scenario
  5. Desktop-shortcut not created by installer (installer script audit)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Test environment setup
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]

import sys
sys.path.insert(0, str(ROOT / "server"))

from redactor import (
    make_replacements,
    collect_findings,
    collect_gazetteer_findings,
)


# ===========================================================================
# 1. Generic label false positives — must NOT be masked
# ===========================================================================

@pytest.mark.parametrize("label_text", [
    "Dane Klienta",
    "Nazwa Spolki",
    "Nazwa Spółki",
    "Adres Siedziby",
    "Dane Strony",
    "Dane Kontrahenta",
    "Numer Umowy",
    "Data Umowy",
    "Postanowienia Końcowe",
    "Postanowienia Ogólne",
    "Warunki Płatności",
    "Przedmiot Umowy",
    "Strony Umowy",
    "Adres Zamieszkania",
    "Adres Korespondencyjny",
])
def test_generic_label_not_masked(label_text: str) -> None:
    """Single-line generic labels must pass through unchanged."""
    masked, replacements = make_replacements(label_text)
    assert masked == label_text, (
        f"Generic label {label_text!r} was unexpectedly masked as: {masked!r}"
    )
    assert replacements == [], (
        f"Generic label {label_text!r} produced replacements: {replacements}"
    )


def test_block_of_generic_labels_unchanged() -> None:
    """The three labels from the audit must all survive unchanged."""
    text = "Dane Klienta\nNazwa Spółki\nAdres Siedziby"
    masked, replacements = make_replacements(text)
    assert masked == text, f"Block of labels was changed: {masked!r}"
    assert replacements == []


def test_labels_preserved_when_mixed_with_real_data() -> None:
    """Labels that introduce actual PII must survive; only the PII is masked."""
    text = "Nazwa Spółki: ABC sp. z o.o.\nAdres Siedziby: ul. Testowa 1, 00-001 Warszawa"
    masked, replacements = make_replacements(text)

    # Labels themselves must not appear in any replacement
    originals = {r.original for r in replacements}
    assert "Nazwa Spółki" not in originals, f"Label appeared in replacements: {originals}"
    assert "Adres Siedziby" not in originals, f"Label appeared in replacements: {originals}"

    # The label text must still be present in the masked output
    assert "Nazwa Spółki" in masked, "Label 'Nazwa Spółki' missing from masked output"
    assert "Adres Siedziby" in masked, "Label 'Adres Siedziby' missing from masked output"

    # Real PII must be masked
    assert "ABC sp. z o.o." not in masked, "Company name not masked"
    assert "ul. Testowa 1" not in masked or "00-001" not in masked, "Address not masked"


# ===========================================================================
# 2. Unbalanced quote — quoted company names
# ===========================================================================

def test_nutrifarm_quoted_company_no_orphan_quote() -> None:
    """Masking 'NUTRIFARM' sp. z o.o. must not leave an unbalanced opening quote."""
    text = 'Klienta = "NUTRIFARM" sp. z o.o. reprezentuje Jan Kowalski.'
    masked, replacements = make_replacements(text)

    # The opening quote must not be left stranded before a placeholder
    assert not re.search(r'[""„\'«‹]\[', masked), (
        f"Orphaned opening quote before placeholder: {masked!r}"
    )
    # The company must be masked
    assert "NUTRIFARM" not in masked, f"Company still visible: {masked!r}"
    # The person must be masked
    assert "Jan Kowalski" not in masked, f"Person still visible: {masked!r}"


def test_nutrifarm_quoted_company_restore_roundtrip() -> None:
    """After masking a quoted company, restore must produce the exact original."""
    text = 'Klienta = "NUTRIFARM" sp. z o.o. reprezentuje Jan Kowalski.'
    masked, replacements = make_replacements(text)

    # Restore manually (no map persistence needed for unit test)
    payload = sorted(
        [{"category": r.category, "original": r.original,
          "placeholder": r.placeholder, "count": r.count}
         for r in replacements],
        key=lambda d: len(d["placeholder"]),
        reverse=True,
    )
    restored = masked
    for entry in payload:
        restored = restored.replace(entry["placeholder"], entry["original"])

    assert restored == text, (
        f"Roundtrip failed.\n  original: {text!r}\n  masked:   {masked!r}\n"
        f"  restored: {restored!r}"
    )


def test_low9_quotation_marks_no_orphan() -> None:
    """Polish low-9 opening quote „ must also be consumed when paired."""
    text = 'Zleceniodawca to „NUTRIFARM" sp. z o.o.'
    masked, replacements = make_replacements(text)
    assert not re.search(r'[""„\'«‹]\[', masked), (
        f"Orphaned opening quote: {masked!r}"
    )


# ===========================================================================
# 3. Gazetteer positive cases — real names still detected
# ===========================================================================

def test_gazetteer_detects_person_without_context() -> None:
    """Bare first-name + surname pair must be detected even without legal context."""
    text = "Jan Kowalski"
    masked, replacements = make_replacements(text)
    assert "Jan Kowalski" not in masked, "Person not masked"
    assert any(r.category == "PERSON" for r in replacements)


def test_gazetteer_detects_person_in_list() -> None:
    """Signatory list with names must be masked."""
    text = "Podpisali: Anna Nowak, Piotr Zieliński."
    masked, replacements = make_replacements(text)
    assert "Anna Nowak" not in masked
    assert "Piotr Zieliński" not in masked
    assert sum(1 for r in replacements if r.category == "PERSON") >= 2


def test_gazetteer_genitive_name_detected() -> None:
    """Inflected genitive 'Jana Kowalskiego' must be detected (via normalization)."""
    findings = collect_gazetteer_findings("Pełnomocnik Jana Kowalskiego")
    found_values = [f.value for f in findings]
    assert any("Kowalskiego" in v or "Kowalski" in v for v in found_values), (
        f"Genitive form not detected; findings: {found_values}"
    )


def test_generic_label_not_in_gazetteer_findings() -> None:
    """Gazetteer must emit zero findings for generic label text."""
    findings = collect_gazetteer_findings(
        "Dane Klienta\nNazwa Spółki\nAdres Siedziby"
    )
    assert findings == [], f"Unexpected gazetteer findings: {findings}"


# ===========================================================================
# 4. Desktop shortcut — must NOT be auto-created by installer
# ===========================================================================

def test_install_csm_does_not_call_create_desktop_shortcut() -> None:
    """install-csm.ps1 must not unconditionally run create-desktop-shortcut.ps1.

    The desktop shortcut was removed from the install flow in rc18 because the
    Word taskpane service panel makes it redundant.  Verified by checking that
    the active (non-commented) code in install-csm.ps1 does not reference the
    shortcut script.
    """
    script = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    active_lines = [
        line for line in script.splitlines()
        if not line.strip().startswith("#")
    ]
    active_text = "\n".join(active_lines)
    assert "create-desktop-shortcut" not in active_text, (
        "install-csm.ps1 still calls create-desktop-shortcut — "
        "desktop shortcut must not be created automatically in rc18"
    )


def test_iss_installer_no_desktop_icon() -> None:
    """Inno Setup script must not create a desktop shortcut in [Icons]."""
    iss = (ROOT / "installer" / "CSM-Setup.iss").read_text(encoding="utf-8")
    # {commondesktop} and {userdesktop} are the standard Inno Setup tokens for desktop
    assert "{commondesktop}" not in iss, "ISS creates a desktop icon via {commondesktop}"
    assert "{userdesktop}" not in iss, "ISS creates a desktop icon via {userdesktop}"
