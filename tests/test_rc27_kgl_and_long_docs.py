from __future__ import annotations

import time

from redactor import make_replacements, mask_ooxml, restore_ooxml, ooxml_to_text


def _payload(replacements):
    return [r.__dict__ for r in replacements]


def test_law_firm_with_comma_partner_surname_is_masked_as_one_company():
    text = "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp.j. reprezentuje klienta."
    masked, replacements = make_replacements(text)

    assert "Kantorowski" not in masked
    assert "Głąb" not in masked
    assert "Wspólnicy" not in masked
    assert masked.startswith("[FIRMA_1]")
    assert any("Kantorowski, Głąb i Wspólnicy" in r.original for r in replacements)


def test_kgl_law_firm_is_masked_with_other_or_missing_legal_form():
    cases = [
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp. j. prowadzi sprawę.",
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy spółka jawna prowadzi sprawę.",
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy spółka partnerska prowadzi sprawę.",
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy sp. z o.o. prowadzi sprawę.",
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy prowadzi sprawę.",
    ]
    for text in cases:
        masked, replacements = make_replacements(text)
        assert "Kantorowski" not in masked
        assert "Głąb" not in masked
        assert "Wspólnicy" not in masked
        assert any(r.category == "COMPANY" and "Kantorowski, Głąb i Wspólnicy" in r.original for r in replacements)


def test_law_firm_with_comma_partner_surname_roundtrip_in_split_ooxml_runs():
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body><w:p>'
        '<w:r><w:t>Kancelaria Prawna Kantorowski</w:t></w:r>'
        '<w:r><w:t>, </w:t></w:r>'
        '<w:r><w:t>Głąb i Wspólnicy Sp.j.</w:t></w:r>'
        '<w:r><w:t> reprezentuje klienta.</w:t></w:r>'
        '</w:p></w:body></w:document>'
    )
    masked_xml, replacements = mask_ooxml(xml)

    assert "Kantorowski" not in masked_xml
    assert "Głąb" not in masked_xml
    assert "Wspólnicy" not in masked_xml
    assert "[FIRMA_1]" in masked_xml

    restored = restore_ooxml(masked_xml, _payload(replacements))
    restored_text = ooxml_to_text(restored)
    assert "Kancelaria Prawna Kantorowski" in restored_text
    assert "Głąb i Wspólnicy Sp.j." in restored_text


def test_long_ooxml_with_many_runs_masks_with_indexed_replacement_path():
    para = (
        '<w:p>'
        '<w:r><w:t>Umowę zawiera Jan Kowalski, PESEL 80010112345, z </w:t></w:r>'
        '<w:r><w:t>Kancelaria Prawna Kantorowski</w:t></w:r>'
        '<w:r><w:t>, </w:t></w:r>'
        '<w:r><w:t>Głąb i Wspólnicy Sp.j.</w:t></w:r>'
        '<w:r><w:t>.</w:t></w:r>'
        '</w:p>'
    )
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:body>' + para * 400 + '</w:body></w:document>'
    )

    start = time.perf_counter()
    masked_xml, replacements = mask_ooxml(xml)
    elapsed = time.perf_counter() - start

    assert "Głąb" not in masked_xml
    assert "Kantorowski" not in masked_xml
    assert any(r.category == "COMPANY" for r in replacements)
    assert elapsed < 6.0
