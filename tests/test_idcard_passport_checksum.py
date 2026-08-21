"""Regresja walidacji dokumentów tożsamości: walidacja sumy kontrolnej dla IDCARD_PL / PASSPORT_PL.

Przed poprawką `category_ok` dla IDCARD_PL i PASSPORT_PL sprawdzała tylko
format (regex), więc każdy ciąg [A-Z]{3}\\d{6} albo [A-Z]{2}\\d{7} był
maskowany — co dawało dużą liczbę false-positive (kody magazynowe,
sygnatury wewnętrzne itp.).

Po poprawce używamy `valid_idcard_pl` / `valid_passport_pl` z validators.py
(które już istniały, ale nie były podpięte do silnika).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from redactor import make_replacements  # noqa: E402


def _placeholders_by_original(text):
    _, reps = make_replacements(text)
    return {(r.category, r.original): r.placeholder for r in reps}


def test_valid_idcard_with_correct_checksum_is_masked():
    text = "Powód okazał dowód osobisty ABA300000."
    plan = _placeholders_by_original(text)
    assert ("IDCARD_PL", "ABA300000") in plan, (
        "Real Polish ID card number with valid checksum must be masked"
    )


def test_random_letters_digits_without_valid_checksum_not_masked_as_idcard():
    text = "Kod magazynowy ABC123456 oraz indeks XYZ999999 nie powinny być dowodami."
    _, reps = make_replacements(text)
    idcard_originals = {r.original for r in reps if r.category == "IDCARD_PL"}
    assert "ABC123456" not in idcard_originals
    assert "XYZ999999" not in idcard_originals


def test_invalid_passport_checksum_not_masked():
    """A random 2-letter+7-digit sequence without a valid passport checksum
    must not be misclassified as PASSPORT_PL."""
    text = "Numer faktury AB1234567 nie jest paszportem."
    _, reps = make_replacements(text)
    passport_originals = {r.original for r in reps if r.category == "PASSPORT_PL"}
    assert "AB1234567" not in passport_originals


def test_full_cycle_after_checksum_change_does_not_break_other_categories():
    """Regression fix must not regress detection of other categories."""
    text = (
        "Powódka Anna Kowalska (PESEL 44051401359, NIP 525-21-12-379) "
        "zawarła umowę z firmą ABC sp. z o.o. KRS 0000123456."
    )
    masked, reps = make_replacements(text)
    cats = {r.category for r in reps}
    assert "PERSON" in cats
    assert "PESEL" in cats
    assert "NIP" in cats
    assert "Anna Kowalska" not in masked
    assert "44051401359" not in masked


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK: IDCARD_PL / PASSPORT_PL checksum tests passed")
