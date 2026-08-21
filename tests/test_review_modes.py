import io
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

import api  # noqa: E402
import redactor  # noqa: E402
from redactor import (  # noqa: E402
    collect_light_residual_review_findings,
    find_residual_risks,
    make_replacements,
    restore_ooxml_package_bytes,
)


client = TestClient(api.app)
HDR = {"X-CSM-Token": "test-token"}


def _tiny_docx_with_text(text: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>"
    )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", xml)
    return out.getvalue()


def test_standard_review_mode_does_not_call_bielik(monkeypatch):
    monkeypatch.setattr(api, "_bielik_enabled_fn", lambda: True)
    monkeypatch.setattr(api, "collect_bielik_deep_review_findings", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Bielik called")))

    response = client.post("/mask", headers=HDR, json={"text": "Anna Nowak podpisała umowę.", "review_mode": "standard"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_mode"] == "standard"
    assert body["bielik_used"] is False


def test_light_review_mode_does_not_require_bielik(monkeypatch):
    monkeypatch.setattr(api, "_bielik_enabled_fn", lambda: True)
    monkeypatch.setattr(api, "_bielik_reachable", lambda: (_ for _ in ()).throw(AssertionError("light must not probe Bielik")))

    response = client.post("/mask", headers=HDR, json={"text": "Anna Nowak, PESEL 44051401359.", "review_mode": "light"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_mode"] == "light"
    assert body["bielik_used"] is False


def test_bielik_review_mode_unavailable_returns_warning_not_failure(monkeypatch):
    monkeypatch.setattr(api, "_bielik_enabled_fn", lambda: True)
    monkeypatch.setattr(api, "_bielik_reachable", lambda: False)
    monkeypatch.setattr(api, "collect_bielik_deep_review_findings", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("unreachable Bielik must not be called")))

    response = client.post("/mask", headers=HDR, json={"text": "Anna Nowak podpisała umowę.", "review_mode": "bielik"})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["review_mode"] == "bielik"
    assert body["bielik_used"] is False
    assert any("Bielik niedostępny" in warning for warning in body["warnings"])


def test_restore_ooxml_package_does_not_call_detectors(monkeypatch):
    monkeypatch.setattr(redactor, "collect_bielik_findings", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("restore called Bielik")))
    monkeypatch.setattr(redactor, "collect_gliner_residual_findings", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("restore called GLiNER")))
    monkeypatch.setattr(redactor, "collect_light_residual_review_findings", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("restore called residual review")))

    replacements = [{"category": "PERSON", "original": "Jan Kowalski", "placeholder": "[OSOBA_1]", "count": 1}]
    restored_bytes, report = restore_ooxml_package_bytes(_tiny_docx_with_text("[OSOBA_1]"), replacements)

    with zipfile.ZipFile(io.BytesIO(restored_bytes), "r") as zf:
        restored_xml = zf.read("word/document.xml").decode("utf-8")
    assert "Jan Kowalski" in restored_xml
    assert report["restored_occurrences"] == 1


def test_light_review_warnings_do_not_disclose_values():
    text = "Jan Kowalski zawarł umowę z FENIX sp. z o.o."
    _masked, replacements = make_replacements(text)
    unsafe_output = "[OSOBA_1] zawarł umowę z FENIX sp. z o.o."

    warnings = collect_light_residual_review_findings(unsafe_output, replacements)
    joined = "\n".join(warnings)

    assert warnings
    assert "Jan Kowalski" not in joined
    assert "FENIX" not in joined


def test_light_review_detects_hyphenated_foreign_person_name_without_disclosing_it():
    risks = find_residual_risks("Umowę podpisał Jean-Luc Picard reprezentujący Starfleet GmbH.")
    joined = "\n".join(risks)

    assert any("możliwe imię i nazwisko" in risk for risk in risks)
    assert "Jean-Luc Picard" not in joined


def test_generic_headings_are_not_masked():
    masked, replacements = make_replacements("Dane Klienta\nNazwa Spółki\nPostanowienia Końcowe")

    assert replacements == []
    assert "[OSOBA_" not in masked
    assert "[FIRMA_" not in masked


def test_mask_restore_roundtrip_stays_one_to_one():
    text = "Anna Nowak, PESEL 44051401359, e-mail anna@example.com."
    masked, replacements = make_replacements(text)
    restored = masked
    for replacement in replacements:
        restored = restored.replace(replacement.placeholder, replacement.original)

    assert restored == text
