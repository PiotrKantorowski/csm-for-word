import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("CSM_API_TOKEN", "test-token")

from redactor import make_replacements  # noqa: E402


def test_contextual_person_detection_masks_inflected_parties_and_alternate_names():
    text = """1. FENIX Sp. z o.o., PESEL: 12345678901 zamieszkała: ______
2. Iryną Bilousovą (po zmianie imienia i nazwiska: Stella Irbis), PESEL: 12345678902 — działającą wspólnie z mężem Aleksandrem Miszczuk (poz. 3) na zasadzie wspólności ustawowej majątkowej małżeńskiej zamieszkałą: ______
3. Aleksandrem Miszczuk, PESEL: 12345678903 — działającym wspólnie z małżonką Iryną Bilousovą (poz. 2) na zasadzie wspólności ustawowej majątkowej małżeńskiej do udziału 4/9 zamieszkały: ______
4. Janem Kowalskim, PESEL: 12345678904 zamieszkała: ______
5. Andrzejem Worosz, PESEL: 12345678905 zamieszkały: ______
6. Lucjanem Worosz, PESEL: 12345678906 zamieszkały: ______
zwanymi dalej Sprzedający
"""
    masked, replacements = make_replacements(text)

    leaked_fragments = [
        "Iryną Bilousovą",
        "Stella Irbis",
        "Aleksandrem Miszczuk",
        "Andrzejem Worosz",
        "Lucjanem Worosz",
        "12345678901",
        "12345678906",
    ]
    for fragment in leaked_fragments:
        assert fragment not in masked
    assert "[OSOBA_1]" in masked
    assert "[OSOBA_2]" in masked
    assert "[OSOBA_3]" in masked
    assert "[OSOBA_5]" in masked
    assert "[PESEL_6]" in masked
    # Generic party roles are not confidential aliases and should remain useful
    # in the anonymized legal text.
    assert "zwanymi dalej Sprzedający" in masked
    assert "Sprzedający" not in {r.original for r in replacements}


def test_company_code_alias_stays_linked_to_its_own_company_not_previous_party():
    text = """Umowa na rzecz FENIX Sp. z o.o.
zawarta pomiędzy:
FENIX Sp. z o.o. zwaną dalej Klientem
a
ZXCV Spółka z ograniczoną odpowiedzialnością sp. k., zwaną dalej ZXCV
Klient oraz ZXCV określani są jako Strony.
FENIX Sp. z o.o. oraz ZXCV potwierdzają warunki.
"""
    masked, replacements = make_replacements(text)
    by_original = {r.original: r.placeholder for r in replacements}

    assert by_original["ZXCV"].startswith("[FIRMA_2_ALIAS_")
    assert "[FIRMA_1_ALIAS" not in by_original["ZXCV"]
    assert "[FIRMA_2_ALIAS_1]" in masked


def test_generic_project_zlecenia_is_not_masked_as_project_identifier():
    text = "Po otrzymaniu założeń, ZXCV opracuje projekt Zlecenia i przekaże projekt do akceptacji Klienta."
    masked, replacements = make_replacements(text)

    assert "projekt Zlecenia" in masked
    assert "przekaże projekt" in masked
    assert not any(r.category == "PROJECT" for r in replacements)
