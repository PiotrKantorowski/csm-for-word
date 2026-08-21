from pathlib import Path

from redactor import make_replacements, mask_ooxml_package_bytes, docx_package_to_text


def test_legal_profiles_mask_id_card_with_inflected_document_phrase_and_nr():
    text = "legitymującą się dowodem osobistym seria AXN nr 584219 oraz dowodem osobistym seria DAP nr 742913"
    out, reps = make_replacements(text)
    assert "AXN" not in out
    assert "584219" not in out
    assert "DAP" not in out
    assert "742913" not in out
    assert out.count("[DOWOD_OSOBISTY_") == 2


def test_legal_profiles_mask_multi_part_people_in_contract_tables_and_appendices():
    text = (
        "Zamawiający - reprezentacja\ue000Michał Adam Nowacki, Prezes Zarządu, PESEL testowy 77021500000\n"
        "Osoba kontaktowa do spraw rozliczeń: Paweł Marek Lis, e-mail: lis@example.pl\n"
        "Wykonawca - zastępstwo awaryjne\ue000Marta Joanna Wrona, konsultantka procesowa"
    )
    out, reps = make_replacements(text)
    for leaked in ["Michał", "Nowacki", "Paweł", "Marek", "Lis", "Marta", "Joanna", "Wrona", "77021500000", "lis@example.pl"]:
        assert leaked not in out
    assert "Prezes Zarządu" in out


def test_legal_profiles_mask_ceidg_trade_names_contract_codes_birth_family_and_po_box():
    text = (
        "Numer umowy\ue000KGL/AMZ/B2B/05/2026/FIK\n"
        "Firma przedsiębiorcy\ue000AMZ Consulting Anna Maria Zielińska\n"
        "Adres do doręczeń\ue000skrytka pocztowa 24, 37-700 Przemyśl 1\n"
        "Data i miejsce urodzenia\ue00023 kwietnia 1988 r., Jarosław\n"
        "Imiona rodziców\ue000Ewa i Tomasz\n"
        "Nazwisko rodowe\ue000Wójcik"
    )
    out, reps = make_replacements(text)
    for leaked in ["KGL", "AMZ", "Anna", "Zielińska", "skrytka pocztowa", "Przemyśl", "23 kwietnia", "Jarosław", "Ewa", "Tomasz", "Wójcik"]:
        assert leaked not in out
    assert "B2B/05/2026/FIK" in out


def test_legal_profiles_mask_sole_proprietor_and_signatures_without_tables():
    text = (
        "Adamem Nowakiem prowadzącym działalność gospodarczą pod firmą Adam Nowak Omnitex, "
        "legitymującym się dowodem osobistym seria DAP nr 742913, zwanym dalej Omnitex.\n"
        "Novus Sp. z o.o.\tAdam Nowak\n"
        "Ewa Malinowska - Prezes Zarządu\tAdam Nowak Omnitex"
    )
    out, reps = make_replacements(text)
    for leaked in ["Adam", "Nowak", "Omnitex", "Ewa", "Malinowska", "DAP", "742913"]:
        assert leaked not in out
    assert "Prezes Zarządu" in out


def test_uploaded_b2b_fixtures_do_not_leave_known_test_identifiers():
    fixtures = [
        Path('/mnt/data/fikcyjna_umowa_b2b_ceidg_bez_tabel.docx'),
        Path('/mnt/data/fikcyjna_umowa_b2b_ceidg_final.docx'),
        Path('/mnt/data/umowa_novus_omnitex_profesjonalna_bez_tabel.docx'),
    ]
    known_leaks = [
        "Michał", "Nowacki", "Anna Maria Zielińska", "Julia Maria Król", "Paweł Marek Lis",
        "AZL 000000", "ANA 000000", "KGL", "AMZ", "kgl-commerce", "amz-consulting", "770215", "880423",
        "Wójcik", "Jarosław", "Novus", "Omnitex", "Ewa Malinowska", "Adam Nowak", "AXN nr 584219", "DAP nr 742913",
        "584219", "742913", "novus-spzoo", "omnitex-it", "Karolina Brzezińska",
    ]
    for fixture in fixtures:
        if not fixture.exists():
            continue
        masked, reps, meta = mask_ooxml_package_bytes(fixture.read_bytes())
        text = docx_package_to_text(masked)
        for leaked in known_leaks:
            assert leaked not in text, f"{fixture.name} still contains {leaked!r}"
