from redactor import make_replacements, _restore_text_value, mask_ooxml, restore_ooxml, ooxml_to_text


def _roundtrip_text(text: str):
    masked, replacements = make_replacements(text)
    restored, report = _restore_text_value(masked, [r.__dict__ for r in replacements])
    assert restored == text
    assert report["leftover_total_after_restore"] == 0
    return masked, replacements


def test_rc32_restore_remains_reversible_for_new_surname_patterns():
    text = (
        "Powód Jedliński złożył pozew. "
        "Pozwany Głąb wniósł odpowiedź. "
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp.j. reprezentowana przez r.pr. Annę Żuchowską-Czernię."
    )
    masked, replacements = _roundtrip_text(text)
    assert "Jedliński" not in masked
    assert "Głąb" not in masked
    assert "Żuchowską-Czernię" not in masked
    assert any(r.original == "Jedliński" for r in replacements)
    assert any(r.original == "Głąb" for r in replacements)


def test_rc32_glab_and_jedlinski_are_masked_in_legal_contexts():
    cases = [
        "Głąb wniósł apelację.",
        "Jedliński złożył oświadczenie.",
        "Pozwany Głąb wniósł odpowiedź na pozew.",
        "Powód Jedliński złożył pozew o zapłatę.",
        "Mec. Głąb wniósł apelację.",
        "r.pr. Jedliński podpisał pismo.",
    ]
    for text in cases:
        masked, replacements = _roundtrip_text(text)
        assert "Głąb" not in masked
        assert "Jedliński" not in masked
        assert replacements


def test_rc32_single_surname_guards_against_common_false_positives():
    for text in [
        "Warszawa wskazała nowe zasady.",
        "Umowa została podpisana.",
        "Sąd wskazał, że pozew oddalono.",
        "Strona złożyła dokumenty w terminie.",
    ]:
        masked, replacements = make_replacements(text)
        assert masked == text
        assert replacements == []


def test_rc32_ooxml_restore_roundtrip_for_new_surname_patterns():
    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>'
        'Powód Jedliński złożył pozew. Pozwany Głąb wniósł odpowiedź.'
        '</w:t></w:r></w:p></w:body></w:document>'
    )
    masked_xml, replacements = mask_ooxml(xml)
    assert "Jedliński" not in masked_xml
    assert "Głąb" not in masked_xml
    restored_xml = restore_ooxml(masked_xml, [r.__dict__ for r in replacements])
    restored_text = ooxml_to_text(restored_xml)
    assert "Powód Jedliński złożył pozew" in restored_text
    assert "Pozwany Głąb wniósł odpowiedź" in restored_text
    assert "[OSOBA_" not in restored_text
