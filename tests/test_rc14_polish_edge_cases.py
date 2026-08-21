from redactor import make_replacements, _restore_text_value


def _mask(text):
    masked, replacements = make_replacements(text)
    payload = [r.__dict__ for r in replacements]
    restored, report = _restore_text_value(masked, payload)
    assert restored == text
    return masked, replacements


def test_title_plus_single_surname_is_masked_without_masking_bare_common_word():
    text = "Pani Mucha złożyła wniosek. Mucha była widoczna w salonie."
    masked, replacements = _mask(text)
    assert "Pani [OSOBA_" in masked
    assert "Mucha była widoczna" in masked
    assert any(r.category == "PERSON" and r.original == "Mucha" for r in replacements)


def test_przeciwko_uppercase_company_without_suffix_is_masked():
    text = "Powód Jan Nowak wnosi pozew przeciwko OLIMP LABORATORIES."
    masked, replacements = _mask(text)
    assert "[OSOBA_" in masked
    assert "przeciwko [FIRMA_" in masked
    assert "OLIMP LABORATORIES" not in masked
    assert any(r.category in {"CONTRACTOR", "COMPANY"} and r.original == "OLIMP LABORATORIES" for r in replacements)


def test_party_label_is_not_swallowed_into_company_placeholder():
    text = "Pozwany Mucha sp. z o.o. z siedzibą w Pustyni wnosi odpowiedź."
    masked, replacements = _mask(text)
    assert masked.startswith("Pozwany [FIRMA_")
    assert not masked.startswith("[FIRMA_")
    assert any(r.category == "COMPANY" and r.original == "Mucha sp. z o.o." for r in replacements)
