"""RC8 regression tests: ordinary-word surnames (Mucha), localities (Pustynia),
multi-word brand names (Meble New Concept), and installer-flow checks.

These tests guard against false-negative anonymization where common Polish words
that double as surnames or locality names were not masked because the first name
was missing from the lexicon, or because the address pattern required a street
prefix, or because the company-name trimmer incorrectly stripped brand words.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("CSM_API_TOKEN", "test-token")

from redactor import make_replacements  # noqa: E402


# ---------------------------------------------------------------------------
# Mucha surname (common word = fly; used as a surname)
# ---------------------------------------------------------------------------

def test_jan_mucha_full_name_is_masked():
    text = "Jan Mucha, PESEL: 12345678901 zamieszkaly: ul. Testowa 1, 00-001 Warszawa."
    masked, _ = make_replacements(text)
    assert "Mucha" not in masked
    assert "Jan" not in masked


def test_renata_mucha_full_name_is_masked():
    text = "Renata Mucha, PESEL: 12345678902 zamieszkala: ul. Lipowa 3, 00-002 Krakow."
    masked, _ = make_replacements(text)
    assert "Mucha" not in masked
    assert "Renata" not in masked


def test_mucha_surname_alias_masked_when_sole_bearer():
    """When only one person named Mucha appears, the bare surname is also masked."""
    text = "Jan Mucha, PESEL: 12345678901. Mucha jest zobowiazany do wykonania zlecenia."
    masked, _ = make_replacements(text)
    assert "Jan Mucha" not in masked
    assert "12345678901" not in masked
    # full-name occurrence masked
    assert "[OSOBA_1]" in masked
    # standalone surname masked as alias
    assert "Mucha" not in masked


def test_patryk_kowalski_is_masked():
    text = "Patryk Kowalski, PESEL: 12345678903 zamieszkaly: ul. Kwiatowa 5, 00-003 Gdansk."
    masked, _ = make_replacements(text)
    assert "Patryk" not in masked
    assert "Kowalski" not in masked


# ---------------------------------------------------------------------------
# Pustynia locality (ordinary word = desert; also a real village name)
# ---------------------------------------------------------------------------

def test_pustynia_rural_address_is_masked():
    """Village address without street prefix must be detected and masked."""
    text = "Pustynia 84F, 39-200 Debica"
    masked, _ = make_replacements(text)
    assert "Pustynia" not in masked
    assert "84F" not in masked


def test_siedziba_w_pustyni_locality_is_masked():
    """'z siedzibą w Pustyni' should not leak the locality name."""
    text = "z siedziba w Pustyni, Pustynia 84F, 39-200 Debica"
    masked, _ = make_replacements(text)
    assert "Pustyni" not in masked
    assert "Pustynia" not in masked


def test_anna_pustynia_person_is_masked():
    """Pustynia used as a surname attached to first name Anna."""
    text = "Anna Pustynia, PESEL: 12345678904 zamieszkala: Pustynia 84F, 39-200 Debica."
    masked, _ = make_replacements(text)
    assert "Anna Pustynia" not in masked
    assert "Anna" not in masked


# ---------------------------------------------------------------------------
# Meble New Concept (brand name where first two tokens look like a person name)
# ---------------------------------------------------------------------------

def test_meble_new_concept_full_name_is_masked():
    """Full company name 'Meble New Concept Sp. z o.o.' must be masked entirely."""
    text = "Meble New Concept Sp. z o.o., NIP: 1234567890."
    masked, _ = make_replacements(text)
    assert "Meble" not in masked
    assert "New" not in masked
    assert "Concept" not in masked


def test_meble_new_concept_alias_is_linked():
    """Short alias introduced after 'dalej:' must map to the same company family."""
    text = (
        "Meble New Concept Sp. z o.o., NIP: 1234567890 (dalej: MNC). "
        "MNC jest zobowiazana do dostarczenia mebli."
    )
    masked, replacements = make_replacements(text)
    assert "Meble" not in masked
    assert "Concept" not in masked
    # Both the full name and the MNC alias must be replaced
    categories = {r.category for r in replacements}
    assert "COMPANY" in categories or "CONTRACTOR" in categories


def test_trim_does_not_strip_brand_prefix_when_not_a_person():
    """'Meble New' must NOT be trimmed as a fake person name from the company match."""
    text = "Meble New Concept sp. z o.o. NIP: 1234567890"
    masked, _ = make_replacements(text)
    assert "Meble" not in masked
    assert "New" not in masked
    assert "Concept" not in masked
    assert "1234567890" not in masked


# ---------------------------------------------------------------------------
# Combined scenario – mixed persons and company in one document
# ---------------------------------------------------------------------------

def test_combined_ordinary_word_document():
    text = (
        "Sprzedawca: Jan Mucha, PESEL: 11111111111, zamieszkaly: ul. Glowna 1, 00-001 Warszawa.\n"
        "Kupujacy: Renata Mucha, PESEL: 22222222222.\n"
        "Dostawca: Meble New Concept Sp. z o.o., NIP: 3333333333, "
        "z siedziba w Pustyni, Pustynia 84F, 39-200 Debica (dalej: MNC).\n"
        "MNC jest zobowiazana do dostarczenia towaru.\n"
    )
    masked, _ = make_replacements(text)
    for leaked in ["Jan Mucha", "Renata Mucha", "Meble New Concept", "Meble", "Concept",
                   "Pustynia", "Pustyni", "11111111111", "22222222222", "3333333333"]:
        assert leaked not in masked, f"Value still visible in anonymized output: {leaked!r}"


# ---------------------------------------------------------------------------
# Installer-flow: setup-once.ps1 FromInstaller switch
# ---------------------------------------------------------------------------

def test_setup_once_has_from_installer_switch():
    """setup-once.ps1 must declare -FromInstaller switch and handle it without
    calling Require-LicenseAcceptance when the switch is set."""
    setup_once = ROOT / "tools" / "setup-once.ps1"
    content = setup_once.read_text(encoding="utf-8", errors="replace")
    assert "[switch]$FromInstaller" in content, "Missing -FromInstaller switch"
    assert "elseif ($FromInstaller)" in content, "Missing elseif branch for FromInstaller"
    # The Require-LicenseAcceptance call must NOT appear in the FromInstaller branch
    lines = content.splitlines()
    in_from_installer_branch = False
    for line in lines:
        stripped = line.strip()
        if "elseif ($FromInstaller)" in stripped:
            in_from_installer_branch = True
        elif in_from_installer_branch and stripped.startswith("}"):
            in_from_installer_branch = False
        if in_from_installer_branch and "Require-LicenseAcceptance" in stripped:
            raise AssertionError("Require-LicenseAcceptance must not be called in the FromInstaller branch")


def test_inno_setup_has_runasoriginaluser():
    """CSM-Setup.iss [Run] section must include runasoriginaluser flag."""
    iss = ROOT / "installer" / "CSM-Setup.iss"
    content = iss.read_text(encoding="utf-8", errors="replace")
    assert "runasoriginaluser" in content, "Missing runasoriginaluser in CSM-Setup.iss [Run]"


def test_install_csm_passes_from_installer_when_source_root_set():
    """install-csm.ps1 must pass -FromInstaller to setup-once.ps1 when
    $OriginalSourceRoot is non-empty (i.e. launched from the GUI installer)."""
    install_csm = ROOT / "tools" / "install-csm.ps1"
    content = install_csm.read_text(encoding="utf-8", errors="replace")
    assert "-FromInstaller" in content, "install-csm.ps1 must pass -FromInstaller to setup-once.ps1"


def test_pani_iwony_teresy_ustrzyckiej_with_pesel_parenthesis_is_masked():
    """Genitive multi-part female names after title and before '(PESEL: ...)' must not leak."""
    text = "na rzecz Pani Iwony Teresy Ustrzyckiej (PESEL: 12345678905)"
    masked, _ = make_replacements(text)
    assert "Iwony" not in masked
    assert "Teresy" not in masked
    assert "Ustrzyckiej" not in masked
    assert "12345678905" not in masked
