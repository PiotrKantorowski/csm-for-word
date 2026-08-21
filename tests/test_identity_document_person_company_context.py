from redactor import make_replacements


def test_contextual_id_card_without_checksum_is_masked_after_label():
    text = "dowód osobisty seria AZL 000000, wydany fikcyjnie przez Prezydenta Miasta Przemyśla"
    out, reps = make_replacements(text)
    assert "AZL 000000" not in out
    assert "[DOWOD_OSOBISTY_1]" in out
    assert "Prezydenta Miasta Przemyśla" in out


def test_person_before_role_and_birth_data_masks_full_name_not_only_first_name():
    text = (
        "Reprezentacja Jan Nowacki - Prezes Zarządu\n"
        "Dane reprezentanta Jan Nowacki, ur. 15 lutego 1977 r. w Tarnowie, "
        "PESEL testowy: 00000000000, seria i numer dowodu osobistego: ANA 000000"
    )
    out, reps = make_replacements(text)
    assert "Jan" not in out
    assert "Nowacki" not in out
    assert "ANA 000000" not in out
    assert "[OSOBA_1] - Prezes Zarządu" in out
    assert "[DOWOD_OSOBISTY_1]" in out


def test_contract_number_company_tokens_are_masked_and_reused():
    text = "Numer umowy: NOVUS/OMNITEX/B2B/05/2026/FIK. Oznaczenia NOVUS i OMNITEX używane są dalej."
    out, reps = make_replacements(text)
    assert "NOVUS" not in out
    assert "OMNITEX" not in out
    assert "B2B/05/2026/FIK" in out
    assert out.count("[FIRMA_1]") == 2
    assert out.count("[FIRMA_2]") == 2


def test_polish_person_names_in_deed_context_are_masked():
    text = "Bernardeta Worosz, PESEL 12345678901, dzieci: Lucjan Worosz i Iryna Zaborska"
    out, reps = make_replacements(text)
    assert "Bernardeta" not in out
    assert "Worosz" not in out
    assert "Lucjan" not in out
    assert "Iryna" not in out
    assert "Zaborska" not in out


def test_public_gmina_name_is_not_masked_as_company():
    text = "uchwałą Rady Gminy Przemyśl nr 1/2023 i planistycznym dokumencie"
    out, reps = make_replacements(text)
    assert "Rady Gminy Przemyśl" in out
    assert not any(r.category in {"COMPANY", "COMPANY_ALIAS"} for r in reps)


def test_person_near_business_name_and_inflected_reference_are_masked():
    text = (
        "Dominik Juszczyk Near-Perfect Performance adres [ADRES_1] [NIP_1] "
        "reprezentowany przez Dominika Juszczyka zwaną dalej Powierzającym"
    )
    out, reps = make_replacements(text)
    assert "Dominik Juszczyk" not in out
    assert "Dominika Juszczyka" not in out
    assert "Near-Perfect Performance" in out
