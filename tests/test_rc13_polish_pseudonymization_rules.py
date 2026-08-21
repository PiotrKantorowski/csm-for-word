from redactor import make_replacements


def _roundtrip(text: str):
    masked, replacements = make_replacements(text)
    restored = masked
    for r in sorted(replacements, key=lambda item: len(item.placeholder), reverse=True):
        restored = restored.replace(r.placeholder, r.original)
    return masked, replacements, restored


def test_party_label_person_is_person_not_company():
    text = "Powód Jan Nowak, PESEL 90010112345, wnosi przeciwko Annie Kowalskiej."
    masked, replacements, restored = _roundtrip(text)
    assert "Jan Nowak" not in masked
    assert "Annie Kowalskiej" not in masked
    assert "[OSOBA_" in masked
    assert not any(r.category in {"CONTRACTOR", "COMPANY"} and r.original == "Jan Nowak" for r in replacements)
    assert restored == text


def test_residence_locality_without_street_is_masked_in_address_context():
    text = "Pozwany, według oświadczenia zamieszkały w Pustyni, PESEL 90010112345."
    masked, replacements, restored = _roundtrip(text)
    assert "Pustyni" not in masked
    assert any(r.category == "ADDRESS" and r.original == "Pustyni" for r in replacements)
    assert restored == text


def test_bank_account_after_owner_name_is_masked_even_if_fixture_number_is_fictional():
    text = "Rachunek bankowy Jana Nowaka: PL 12 3456 7890 1234 5678 9012 3456."
    masked, replacements, restored = _roundtrip(text)
    assert "3456 7890 1234 5678 9012 3456" not in masked
    assert any(r.category == "BANK_ACCOUNT" for r in replacements)
    assert restored == text


def test_company_context_still_masks_uppercase_party_company():
    text = "Powód: OLIMP LABORATORIES z siedzibą w Pustyni, NIP 1234567890."
    masked, replacements, restored = _roundtrip(text)
    assert "OLIMP LABORATORIES" not in masked
    assert "1234567890" not in masked
    assert any(r.category in {"CONTRACTOR", "COMPANY"} for r in replacements)
    assert restored == text
