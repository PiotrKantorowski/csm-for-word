from redactor import make_replacements


def test_legal_lexicon_masks_id_card_in_identity_document_table_row():
    text = "Dokumentu tożsamości\ue000dowód osobisty seria AZL 000000, wydany fikcyjnie przez Prezydenta Miasta Przemyśla"
    out, reps = make_replacements(text)
    assert "AZL 000000" not in out
    assert "[DOWOD_OSOBISTY_1]" in out
    assert "Dokumentu tożsamości" in out
    assert "Prezydenta Miasta Przemyśla" in out


def test_legal_lexicon_masks_full_person_in_table_representation_row():
    text = "Reprezentacja\ue000Jan Nowacki - Prezes Zarządu\nDane reprezentanta\ue000Jan Nowacki, ur. [DATE_1] w [LOCATION_1], PESEL [PESEL_1]"
    out, reps = make_replacements(text)
    assert "Jan" not in out
    assert "Nowacki" not in out
    assert "[OSOBA_1] - Prezes Zarządu" in out


def test_legal_lexicon_masks_people_in_deed_and_keeps_public_gmina_name():
    text = (
        "Bernadetta Worosz, PESEL [PESEL_7], a po niej dzieci: Lucjan Worosz, "
        "Maria Worosz i Iryna Zaborska. Uchwałą Rady Gminy Przemyśl nr 1/2023."
    )
    out, reps = make_replacements(text)
    for value in ["Bernadetta", "Lucjan", "Maria Worosz", "Iryna", "Zaborska"]:
        assert value not in out
    assert "Rady Gminy Przemyśl" in out


def test_legal_lexicon_masks_person_in_processing_agreement_intro():
    text = (
        "Dominik Juszczyk Near-Perfect Performance adres [ADRES_1] [NIP_1] "
        "reprezentowany przez Dominika Juszczyka zwaną dalej „Powierzającym”"
    )
    out, reps = make_replacements(text)
    assert "Dominik Juszczyk" not in out
    assert "Dominika Juszczyka" not in out
    assert "Near-Perfect Performance" in out


def test_legal_lexicon_masks_party_codes_inside_contract_number_but_not_noise():
    text = "Numer umowy: NOVUS/OMNITEX/B2B/05/2026/FIK; dalej NOVUS i OMNITEX."
    out, reps = make_replacements(text)
    assert "NOVUS" not in out
    assert "OMNITEX" not in out
    assert "B2B/05/2026/FIK" in out
