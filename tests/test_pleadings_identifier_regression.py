import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from redactor import make_replacements

def cats(text):
    masked, reps = make_replacements(text)
    return masked, [(r.category, r.original, r.placeholder) for r in reps]

def test_pleading_invoice_number_is_not_labeled_as_nip():
    text = "Faktura VAT z dnia 18.12.2024 r. numer: 1234567890, NIP: 5252112379"
    masked, reps = cats(text)
    assert "Faktura VAT z dnia 18.12.2024 r. numer: [DOKUMENT_FINANSOWY_1]" in masked
    assert "NIP: [NIP_1]" in masked
    assert ("FINANCIAL_DOC_ID", "1234567890", "[DOKUMENT_FINANSOWY_1]") in reps
    assert ("NIP", "5252112379", "[NIP_1]") in reps

def test_pleading_order_number_is_masked_as_order_identifier():
    text = "Zlecenie numer 1469375 z dnia 17.12.2024 r.; zamówienie nr 99887766."
    masked, reps = cats(text)
    assert "Zlecenie numer [NR_PROJEKTU_1]" in masked
    assert "zamówienie nr [NR_PROJEKTU_2]" in masked
    assert all(cat == "PROJECT_ID" for cat, _, _ in reps)

def test_court_and_street_address_are_masked_without_leaving_street_tail():
    text = "Sąd Rejonowy w Częstochowie, ul. Dąbrowskiego 23/35, 42-200 Częstochowa"
    masked, reps = cats(text)
    assert masked == "[SAD_1], [ADRES_1]"
    assert "Dąbrowskiego" not in masked
