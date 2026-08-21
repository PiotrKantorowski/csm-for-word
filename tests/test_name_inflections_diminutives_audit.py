from __future__ import annotations

from redactor import make_replacements, collect_findings


def test_inflected_multi_given_names_are_grouped_to_same_person_placeholder():
    text = (
        "Michał Adam Nowacki podpisał umowę. "
        "Z Michałem Adamem Nowackim ustalono termin. "
        "Michała Adama Nowackiego wskazano w załączniku."
    )
    out, replacements = make_replacements(text)
    assert "Michał" not in out
    assert "Michałem" not in out
    assert "Nowackiego" not in out
    person_placeholders = [r.placeholder for r in replacements if r.category == "PERSON"]
    assert "[OSOBA_1]" in person_placeholders
    assert "[OSOBA_1_ALIAS_1]" in person_placeholders
    assert "[OSOBA_1_ALIAS_2]" in person_placeholders


def test_feminine_inflection_for_two_given_names_and_surname():
    text = "Anna Maria Zielińska prowadzi działalność. Annie Marii Zielińskiej doręczono pismo."
    out, replacements = make_replacements(text)
    assert "Anna" not in out
    assert "Annie" not in out
    assert "Zielińskiej" not in out
    assert "[OSOBA_1]" in out
    assert "[OSOBA_1_ALIAS_1]" in out


def test_common_diminutives_are_detected_and_clustered():
    text = (
        "Pełnomocnik Piotrek Kowalski przesłał uwagi. "
        "Ustaliłem z Piotrkiem Kowalskim termin. "
        "Kuba Malinowski potwierdził odbiór, a Jakuba Malinowskiego wezwano. "
        "Ania Kowalska przesłała załącznik, z Anią Kowalską omówiono sprawę."
    )
    out, replacements = make_replacements(text)
    leaked = ["Piotrek", "Piotrkiem", "Kuba", "Jakuba", "Ania", "Anią", "Kowalski", "Malinowski"]
    for value in leaked:
        assert value not in out
    assert "przesłał uwagi" in out
    assert "[OSOBA_" in out
    assert all(r.original != "uwagi" for r in replacements)


def test_role_prefix_is_not_part_of_person_value():
    text = "Pełnomocnik Piotrek Kowalski przesłał uwagi."
    findings = collect_findings(text)
    assert any(f.category == "PERSON" and f.value == "Piotrek Kowalski" for f in findings)
    assert all(f.value != "Pełnomocnik Piotrek Kowalski" for f in findings)
    assert all(f.value != "uwagi" for f in findings)
