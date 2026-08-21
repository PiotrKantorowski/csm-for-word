"""RC34 edge hardening for public business/legal documents.

Scope: no court judgments and no blank forms. These tests cover public-register,
procurement, property and B2B appendix structures that remained weaker after RC33.
"""

from __future__ import annotations

from redactor import _restore_text_value, make_replacements


def _roundtrip(text: str):
    masked, replacements = make_replacements(text)
    restored, report = _restore_text_value(masked, [r.__dict__ for r in replacements])
    assert report["all_found"], report
    assert restored == text
    return masked, replacements


def test_rc34_public_aid_jdg_and_eori_are_masked():
    text = "Beneficjent pomocy: Jan Kowalski Software, NIP 1234567890, EORI PL123456789000000."
    masked, replacements = _roundtrip(text)
    assert "Jan Kowalski Software" not in masked
    assert "1234567890" not in masked
    assert "PL123456789000000" not in masked
    assert any(r.category == "BUSINESS_ID" for r in replacements)


def test_rc34_procurement_and_notice_numbers_do_not_leak_or_become_phone():
    text = "Ogłoszenie BZP nr 2026/BZP 00123456/01 oraz TED 2026/S 123-456789. Postępowanie nr ZP.271.1.2026."
    masked, replacements = _roundtrip(text)
    assert "2026/BZP 00123456/01" not in masked
    assert "2026/S 123-456789" not in masked
    assert "ZP.271.1.2026" not in masked
    originals = {r.original for r in replacements}
    assert "123-456789" not in originals


def test_rc34_reverse_addresses_without_street_prefix_are_masked_as_whole_address():
    for text in [
        "Adres korespondencyjny: 39-200 Dębica, Pustynia 84F.",
        "Adres: 00-001 Warszawa, Prosta 1 lok. 2.",
    ]:
        masked, replacements = _roundtrip(text)
        assert "39-200" not in masked and "00-001" not in masked
        assert "Pustynia 84F" not in masked and "Prosta 1" not in masked
        assert any(r.category == "ADDRESS_FULL" for r in replacements)


def test_rc34_property_unit_identifiers_are_masked():
    text = "Przedmiot obejmuje lokal nr 12 oraz miejsce postojowe MP-45 w garażu nr G-2."
    masked, replacements = _roundtrip(text)
    assert "lokal nr 12" not in masked
    assert "MP-45" not in masked
    assert "G-2" not in masked
    assert any(r.category == "PROPERTY_UNIT_ID" for r in replacements)


def test_rc34_lei_duns_and_platform_tenant_ids_are_masked():
    text = "Numer LEI: 259400ABCDEFGHIJKL12, DUNS 123456789, vendor_id=VEN-2026-000123, tenant_id=abc-law-tenant."
    masked, replacements = _roundtrip(text)
    for leaked in ["259400ABCDEFGHIJKL12", "123456789", "VEN-2026-000123", "abc-law-tenant"]:
        assert leaked not in masked
    assert sum(1 for r in replacements if r.category == "BUSINESS_ID") >= 4


def test_rc34_full_and_short_business_name_labels_are_masked_without_generic_title_false_positive():
    text = "Nazwa skrócona: KXG Legal, nazwa pełna: Kancelaria Prawna Kantorowski Głąb i Wspólnicy sp.j."
    masked, replacements = _roundtrip(text)
    assert "KXG Legal" not in masked
    assert "Kancelaria Prawna Kantorowski" not in masked
    assert "Głąb" not in masked
    assert any(r.original == "KXG Legal" for r in replacements)

    fp = "Nazwa pełna: Regulamin sklepu internetowego."
    masked_fp, replacements_fp = make_replacements(fp)
    assert masked_fp == fp
    assert replacements_fp == []


def test_rc34_notarial_act_number_is_masked():
    text = "Numer aktu notarialnego NZ/1234/2026, repertorium A 1234/2026."
    masked, replacements = _roundtrip(text)
    assert "NZ/1234/2026" not in masked
    assert "repertorium A 1234/2026" not in masked
    assert sum(1 for r in replacements if r.category == "REPERTORIUM") == 2


def test_rc34_false_positive_guards_for_business_labels_and_property_words():
    for text in [
        "Postępowanie było prowadzone zgodnie z zasadami konkurencyjności.",
        "Ogłoszenie BZP zostanie opublikowane po akceptacji dokumentacji.",
        "Adres korespondencyjny zostanie podany później.",
        "Lokal użytkowy zostanie wydany w terminie.",
        "Nazwa skrócona: dokument testowy.",
    ]:
        masked, replacements = make_replacements(text)
        assert masked == text
        assert replacements == []
