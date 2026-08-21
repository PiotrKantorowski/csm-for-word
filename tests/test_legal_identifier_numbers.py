from redactor import make_replacements


def assert_masked(text, leaks):
    out, reps = make_replacements(text)
    for leak in leaks:
        assert leak not in out, f"leaked {leak!r} in {out!r}"
    return out, reps


def test_masks_land_register_bdo_and_ceidg_identifiers():
    text = (
        "Księga wieczysta nr RZ1Z/00012345/6, numer rejestrowy BDO: 000123456, "
        "Identyfikator wpisu CEIDG: CEIDG-ID-FIK-2026-05-15-001."
    )
    out, reps = assert_masked(text, ["RZ1Z/00012345/6", "000123456", "CEIDG-ID-FIK-2026-05-15-001"])
    assert "[KSIEGA_WIECZYSTA_" in out
    assert "[BDO_" in out
    assert "[NR_CEIDG_" in out


def test_masks_case_refs_repertory_and_admin_ids_but_not_paragraph_numbers():
    text = (
        "Sygn. akt I C 123/24, Rep. A nr 9876/2024, decyzja nr WOOŚ.420.12.2024.AB. "
        "Zgodnie z § 5 ust. 2 i Załącznikiem nr 1 termin wynosi 14 dni."
    )
    out, reps = assert_masked(text, ["I C 123/24", "9876/2024", "WOOŚ.420.12.2024.AB"])
    assert "§ 5 ust. 2" in out
    assert "Załącznikiem nr 1" in out
    assert "14 dni" in out


def test_masks_vehicle_passport_residence_card_professional_and_property_ids():
    text = (
        "VIN: WBA12345678901234, nr rejestracyjny RZ12345, paszport nr AB1234567, "
        "karta pobytu nr PL12345678, PWZ nr 1234567, działka nr 123/4, obręb 0001."
    )
    out, reps = assert_masked(text, ["WBA12345678901234", "RZ12345", "AB1234567", "PL12345678", "1234567", "123/4"])
    assert "[NR_REJESTRACYJNY_" in out
    assert "[PASZPORT_" in out
    assert "[KARTA_POBYTU_" in out
    assert "[UPRAWNIENIA_ZAWODOWE_" in out
    assert "[NR_DZIALKI_" in out
    assert "obręb" in out


def test_masks_e_delivery_policy_claim_shipment_and_project_ids_in_context():
    text = (
        "Adres ePUAP: /KGL/skrytka, adres do doręczeń elektronicznych AE:PL-ABCDE12345, "
        "polisa nr ABC/123456/2025, numer szkody CLM-2025-000123, "
        "list przewozowy nr DHL1234567890, zamówienie nr ZAM/2026/001."
    )
    out, reps = assert_masked(text, ["/KGL/skrytka", "AE:PL-ABCDE12345", "ABC/123456/2025", "CLM-2025-000123", "DHL1234567890", "ZAM/2026/001"])
    assert "[NR_EDORECZENIA_" in out
    assert "[NR_POLISY_" in out
    assert "[NR_PRZESYLKI_" in out
    assert "[NR_PROJEKTU_" in out


def test_does_not_mask_ordinary_numbers_without_context():
    text = "§ 2 ust. 3, Załącznik nr 4, termin 21 dni, kwota 12.500,00 zł, wersja 1.2.3."
    out, reps = make_replacements(text)
    assert out == text
    assert reps == []
