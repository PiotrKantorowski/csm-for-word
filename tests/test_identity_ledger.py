"""Iteration 6 — IdentityLedger stabilisation.

Regression tests for the surname-collision bug, where two distinct people
sharing a surname collapsed into one placeholder family and bare-surname
mentions were misattributed at restore time.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from redactor import (  # noqa: E402
    make_replacements,
    _canonical_person_value,
    _surname_key,
    _first_name_key,
    _person_aliases,
)


def _placeholders_by_original(text):
    _, reps = make_replacements(text)
    return {r.original: r.placeholder for r in reps}


# ─── Canonical identity keys ─────────────────────────────────────────────────

def test_canonical_includes_first_name_so_same_surname_does_not_collide():
    # Same surname, different first names — must produce distinct identity keys
    assert _canonical_person_value("Jan Kowalski") != _canonical_person_value("Piotr Kowalski")
    assert _canonical_person_value("Jan Kowalski") != _canonical_person_value("Anna Kowalska")


def test_canonical_groups_inflected_forms_of_same_person():
    # Different inflected forms of the same person must map to one canonical
    assert _canonical_person_value("Jan Kowalski") == _canonical_person_value("Janem Kowalskim")
    assert _canonical_person_value("Jan Kowalski") == _canonical_person_value("Jana Kowalskiego")


def test_surname_key_normalises_polish_inflections():
    assert _surname_key("Kowalski") == _surname_key("Kowalskiego")
    assert _surname_key("Kowalski") == _surname_key("Kowalskim")
    assert _surname_key("Kowalska") == _surname_key("Kowalskiej")
    # Male and female forms are intentionally distinct identities
    assert _surname_key("Kowalski") != _surname_key("Kowalska")


def test_first_name_key_handles_common_polish_declensions():
    assert _first_name_key("Jan") == _first_name_key("Janem")
    assert _first_name_key("Jan") == _first_name_key("Jana")
    assert _first_name_key("Anna") == _first_name_key("Anną")


# ─── End-to-end masking behaviour ────────────────────────────────────────────

def test_same_surname_different_first_names_get_distinct_placeholders():
    text = "Jan Kowalski podpisał. Piotr Kowalski był świadkiem. Anna Kowalska też podpisała."
    plan = _placeholders_by_original(text)
    assert plan["Jan Kowalski"] != plan["Piotr Kowalski"], (
        "REGRESSION: Jan Kowalski and Piotr Kowalski must not share a placeholder family"
    )
    assert plan["Jan Kowalski"] != plan["Anna Kowalska"]
    assert plan["Piotr Kowalski"] != plan["Anna Kowalska"]


def test_bare_surname_left_visible_when_ambiguous():
    # Two people share the surname "Kowalski" — a bare "Kowalski" is ambiguous
    # and must NOT be silently attributed to either. It is better to leave it
    # unmasked (so the reviewer notices it) than to break restore integrity.
    text = "Jan Kowalski podpisał. Piotr Kowalski się zgodził. Później Kowalski wrócił."
    result, _ = make_replacements(text)
    # The two full names get masked, but bare "Kowalski" stays in plain text.
    assert "Kowalski" in result, "Ambiguous bare surname must remain visible for manual review"
    # And it must definitely not be replaced by either of the existing placeholders.
    assert result.count("[OSOBA_") == 2


def test_bare_surname_masked_when_unique():
    # One person — bare surname after introduction is unambiguous, must mask.
    text = "Jan Kowalski podpisał umowę. Później Kowalski wrócił po dokument."
    result, reps = make_replacements(text)
    assert "Kowalski" not in result.split("[OSOBA_1]")[-1].split("[OSOBA_1_ALIAS_1]")[-1]
    # The alias must point to the same family as the full name
    family_of_full = next(r.placeholder for r in reps if r.original == "Jan Kowalski")
    family_of_alias = next(r.placeholder for r in reps if r.original == "Kowalski")
    assert family_of_full.startswith("[OSOBA_1")
    assert family_of_alias.startswith("[OSOBA_1")


def test_first_name_alone_masked_when_unique():
    # Three Kowalski + one unique Anna — bare "Anna" is unambiguous.
    text = "Jan Kowalski, Piotr Kowalski, Marek Kowalski oraz Anna Nowak. Anna podpisała umowę."
    result, reps = make_replacements(text)
    anna_full = next(r.placeholder for r in reps if r.original == "Anna Nowak")
    anna_alias_reps = [r for r in reps if r.original == "Anna"]
    assert anna_alias_reps, "Unambiguous first name must be masked"
    assert anna_alias_reps[0].placeholder.startswith(anna_full[:-1])


def test_first_name_alone_kept_visible_when_ambiguous():
    # Two people share the first name "Jan" — bare "Jan" must NOT be masked.
    text = "Jan Kowalski i Jan Nowak. Później Jan się odezwał."
    result, _ = make_replacements(text)
    # The two full names get masked
    assert "[OSOBA_1]" in result and "[OSOBA_2]" in result
    # The trailing bare "Jan" stays in plain text
    tail = result.rsplit("[OSOBA_2]", 1)[-1]
    assert "Jan" in tail


def test_inflected_forms_cluster_with_nominative():
    text = "Anna Kowalska zawarła umowę. Pełnomocnik Anny Kowalskiej potwierdził."
    plan = _placeholders_by_original(text)
    # Both surface forms refer to the same person and must use the same family
    full = plan["Anna Kowalska"]
    inflected = plan["Anny Kowalskiej"]
    family = full[:-1]  # strip closing bracket -> e.g. "[OSOBA_1"
    assert inflected.startswith(family), f"Expected same PERSON_N family, got {full} vs {inflected}"


def test_husband_and_wife_get_distinct_placeholders():
    # Polish gendered surnames are distinct identities by design.
    text = "Małżonkowie Jan Kowalski i Anna Kowalska zawarli umowę."
    plan = _placeholders_by_original(text)
    assert plan["Jan Kowalski"] != plan["Anna Kowalska"]


# ─── _person_aliases gating ──────────────────────────────────────────────────

def test_person_aliases_omits_surname_when_include_surname_false():
    aliases = _person_aliases("Jan Kowalski", include_surname=False)
    # The full cross-product forms remain (Jan + Kowalski-variants)
    assert "Jan Kowalski" in aliases
    # But bare-surname forms must be absent
    assert "Kowalski" not in aliases
    assert "Kowalskiego" not in aliases


def test_person_aliases_includes_surname_by_default():
    aliases = _person_aliases("Jan Kowalski")
    assert "Kowalski" in aliases


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK: IdentityLedger regression tests passed")
