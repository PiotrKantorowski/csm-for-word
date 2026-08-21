from pathlib import Path

from redactor import collect_findings, find_residual_risks, make_replacements, _restore_text_value


def _roundtrip(text: str):
    masked, replacements = make_replacements(text)
    restored, report = _restore_text_value(masked, [r.__dict__ for r in replacements])
    assert report["all_found"], report
    assert restored == text
    return masked, replacements


def test_court_detector_stops_before_sentence_verb_and_masks_alias():
    text = (
        "Sąd Okręgowy w Rzeszowie wydał postanowienie. "
        "Następnie SO w Rzeszowie odmówił zabezpieczenia."
    )
    findings = collect_findings(text)
    assert any(f.category == "COURT" and f.value == "Sąd Okręgowy w Rzeszowie" for f in findings), findings
    assert not any("wydał" in f.value for f in findings if f.category == "COURT"), findings
    assert any(f.category == "COURT_ALIAS" and f.value == "SO w Rzeszowie" for f in findings), findings
    masked, replacements = _roundtrip(text)
    assert "wydał postanowienie" in masked
    assert "[SAD_1]" in masked
    assert "SO w Rzeszowie" not in masked
    assert any(r.category == "COURT_ALIAS" for r in replacements)


def test_court_alias_for_m_st_warszawy_roundtrips():
    text = "Sąd Rejonowy dla m.st. Warszawy rozpoznał sprawę. SR dla m.st. Warszawy oddalił wniosek."
    masked, replacements = _roundtrip(text)
    assert "[SAD_1] rozpoznał sprawę" in masked
    assert "SR dla m.st. Warszawy" not in masked
    assert any(r.category == "COURT_ALIAS" for r in replacements)


def test_crossborder_person_and_company_with_latin_diacritics_are_masked():
    text = "Umowę podpisał François Dupont oraz Müller GmbH z siedzibą w Berlinie."
    masked, replacements = _roundtrip(text)
    assert "François Dupont" not in masked
    assert "Müller GmbH" not in masked
    assert any(r.category == "PERSON" and r.original == "François Dupont" for r in replacements)
    assert any(r.category == "COMPANY" and r.original == "Müller GmbH" for r in replacements)


def test_lowercase_legal_person_after_title_is_masked_as_full_span():
    text = "Pełnomocnikiem był radca prawny jan nowak."
    masked, replacements = _roundtrip(text)
    assert "jan nowak" not in masked
    assert "nowak" not in masked
    assert any(r.category == "PERSON" and r.original == "jan nowak" for r in replacements)


def test_optional_gliner_is_safe_when_not_installed_or_disabled(monkeypatch):
    monkeypatch.delenv("CSMW_ENABLE_GLINER", raising=False)
    risks = find_residual_risks("Dokument bez danych osobowych i bez modelu GLiNER.")
    assert isinstance(risks, list)


def test_setup_nlp_optional_uses_project_root_not_tools_subfolder():
    script = Path("tools/setup-nlp-optional.ps1").read_text(encoding="utf-8-sig")
    assert 'Split-Path -Leaf $ScriptDir' in script
    assert '$ServerDir = Join-Path $Root "server"' in script
    assert '$PythonExe = Join-Path $VenvDir "Scripts\\python.exe"' in script
    assert 'Join-Path $Root "server\\.venv\\Scripts\\python.exe"' not in script
    assert r'Join-Path $Root "server\.venv\Scripts\python.exe"' not in script
