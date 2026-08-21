from redactor import make_replacements, _restore_text_value


def _roundtrip(text: str):
    masked, replacements = make_replacements(text)
    restored, report = _restore_text_value(masked, [r.__dict__ for r in replacements])
    assert report["all_found"], report
    assert restored == text
    return masked, replacements


def test_masks_quoted_foreign_company_with_ampersand_and_diacritics():
    text = 'Stroną jest "MÜLLER & Söhne GmbH" z siedzibą w Berlinie.'
    masked, replacements = _roundtrip(text)
    assert "MÜLLER & Söhne GmbH" not in masked
    assert any(r.category == "COMPANY" and r.original == "MÜLLER & Söhne GmbH" for r in replacements)


def test_masks_numeric_birth_date_with_birth_place():
    text = "Jan Kowalski, ur. 1.02.1980 r. w Rzeszowie, PESEL 80010112345."
    masked, replacements = _roundtrip(text)
    assert "1.02.1980" not in masked
    assert "Rzeszowie" not in masked
    assert any(r.category == "BIRTH_DATA" and "Rzeszowie" in r.original for r in replacements)


def test_masks_reverse_order_address_as_one_address_span():
    text = "Adres do korespondencji: 00-001 Warszawa, ul. Prosta 1."
    masked, replacements = _roundtrip(text)
    assert "00-001 Warszawa" not in masked
    assert "ul. Prosta 1" not in masked
    assert any(r.category == "ADDRESS_FULL" and r.original == "00-001 Warszawa, ul. Prosta 1" for r in replacements)


def test_masks_ceidg_business_line_after_entrepreneur_label():
    text = "Przedsiębiorca: Jan Kowalski Software, ul. Prosta 1, 00-001 Warszawa."
    masked, replacements = _roundtrip(text)
    assert "Jan Kowalski Software" not in masked
    assert any(r.category == "CONTRACTOR" and r.original == "Jan Kowalski Software" for r in replacements)


def test_masks_eu_vat_id_without_partial_regon_or_nip_leak():
    text = "VAT UE: DE123456789, NIP UE: PL1234567890, kontrahent: Beispiel GmbH."
    masked, replacements = _roundtrip(text)
    assert "DE123456789" not in masked
    assert "PL1234567890" not in masked
    assert "DE[" not in masked
    assert "PL[" not in masked
    assert sum(1 for r in replacements if r.category == "VAT_ID") == 2


def test_masks_medical_employee_customer_and_english_passport_identifiers():
    text = (
        "Pacjent Jan Kowalski, nr historii choroby HC/2024/123. "
        "Pracownik Anna Nowak, numer kadrowy EMP-2024-0001. "
        "Numer klienta: KLIENT-2025-000123. "
        "Passport No. C01X00T47 został okazany przez John Smith."
    )
    masked, replacements = _roundtrip(text)
    for leak in ["HC/2024/123", "EMP-2024-0001", "KLIENT-2025-000123", "C01X00T47"]:
        assert leak not in masked
    assert "Pracownik [OSOBA_" in masked
    cats = {r.category for r in replacements}
    assert {"MEDICAL_RECORD_ID", "EMPLOYEE_ID", "CUSTOMER_ID", "PASSPORT_CONTEXT"} <= cats
