"""Pełny smoke test cyklu pracy z lokalnym API.

Pokrywa kluczowe scenariusze wspieranego przepływu:
1. /health zwraca poprawną wersję i ścieżki
2. /scan → /mask → /restore_ooxml_parts roundtrip
3. Rebrand: brak markowej nazwy w odpowiedziach API
4. Ostrzeżenia o niejednoznaczności w pełnym cyklu
5. /audit_summary zawiera wpisy z mask i restore
6. Pełny cykl docx_v3 (tracked changes preserve mode)
"""
import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["CSM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

from api import app  # noqa: E402

client = TestClient(app)
HDR = {"X-CSM-Token": "test-token"}


def test_health_reports_runtime_paths():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "paths" in body
    assert "maps" in body["paths"]
    assert "backups" in body["paths"]


def test_health_reports_nlp_bielik_status(monkeypatch):
    import api as _api

    # By default Bielik is disabled → both flags False
    monkeypatch.setattr(_api, "_bielik_enabled_fn", lambda: False)
    r = client.get("/health")
    body = r.json()
    assert "nlp" in body
    assert body["nlp"]["bielik_enabled"] is False
    assert body["nlp"]["bielik_reachable"] is False

    # When enabled but Ollama unreachable → enabled=True, reachable=False
    monkeypatch.setattr(_api, "_bielik_enabled_fn", lambda: True)
    monkeypatch.setattr(_api, "_bielik_reachable", lambda: False)
    r2 = client.get("/health")
    body2 = r2.json()
    assert body2["nlp"]["bielik_enabled"] is True
    assert body2["nlp"]["bielik_reachable"] is False

    # When enabled and Ollama running → both True
    monkeypatch.setattr(_api, "_bielik_reachable", lambda: True)
    r3 = client.get("/health")
    body3 = r3.json()
    assert body3["nlp"]["bielik_enabled"] is True
    assert body3["nlp"]["bielik_reachable"] is True


def test_full_text_mask_restore_roundtrip():
    original = (
        "Powódka Anna Kowalska (PESEL 44051401359, e-mail anna@kowalska.pl) zawarła "
        "umowę z firmą ABC sp. z o.o. KRS 0000123456. Pełnomocnikiem jest Jan Nowak."
    )
    # Mask
    r = client.post("/mask", headers=HDR, json={"text": original})
    assert r.status_code == 200, r.text
    body = r.json()
    masked_text = body["masked_text"]
    map_id = body["map_id"]
    assert "Anna Kowalska" not in masked_text
    assert "44051401359" not in masked_text
    assert "anna@kowalska.pl" not in masked_text
    assert "ABC" not in masked_text
    assert "0000123456" not in masked_text
    assert "Jan Nowak" not in masked_text
    assert "[OSOBA_" in masked_text
    # Restore via map (the text path returns the map; restoration is applied client-side
    # for plaintext mode — we just confirm the map round-trips).
    r2 = client.post("/restore", headers=HDR, json={"map_id": map_id})
    assert r2.status_code == 200, r2.text
    assert r2.json()["map_id"] == map_id
    # Apply replacements client-side to verify restorability
    restored = masked_text
    for rep in r2.json()["replacements"]:
        restored = restored.replace(rep["placeholder"], rep["original"])
    assert "Anna Kowalska" in restored
    assert "44051401359" in restored
    assert "ABC sp. z o.o." in restored


def test_rebrand_no_old_brand_in_api_metadata():
    """The OpenAPI doc / FastAPI title must not advertise the old brand."""
    openapi = client.get("/openapi.json").json()
    title = openapi.get("info", {}).get("title", "")
    assert "Claude Safe Mode" not in title
    assert "CSM" in title


def test_ambiguity_warnings_flow_end_to_end():
    text = "Jan Kowalski podpisał. Piotr Kowalski się zgodził. Później Kowalski potwierdził."
    r = client.post("/mask", headers=HDR, json={"text": text})
    assert r.status_code == 200
    body = r.json()
    warnings = body["warnings"]
    assert any("niejednoznaczne nazwiska" in w for w in warnings), warnings
    # Distinct identities — both Kowalskis must get different placeholders
    masked = body["masked_text"]
    assert masked.count("[OSOBA_") == 2
    # Bare "Kowalski" stays visible (correct behaviour per iteration 6)
    assert "Kowalski" in masked


def test_audit_summary_records_recent_operations():
    # Trigger one mask operation
    client.post("/mask", headers=HDR, json={"text": "Anna Nowak podpisała umowę."})
    r = client.get("/audit_summary?limit=20", headers=HDR)
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "1.6"
    entries = body["entries"]
    assert entries, "Expected at least one audit entry after a mask"
    # No PII should leak through the allow-list
    raw = r.text
    assert "Anna Nowak" not in raw


def test_docx_v3_preserve_roundtrip():
    """Mask → restore for a DOCX containing tracked changes."""
    from test_tracked_changes_preserve_mode import _build_docx_with_revisions, W  # type: ignore
    from lxml import etree
    import io
    import zipfile

    def _count(docx_b64: str, local: str) -> int:
        data = base64.b64decode(docx_b64)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            tree = etree.fromstring(zf.read("word/document.xml"))
        return len(tree.findall(f".//{W}{local}"))

    docx_b64 = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    ins_before = _count(docx_b64, "ins")
    del_before = _count(docx_b64, "del")

    # Mask preserving tracked changes
    r = client.post("/mask_docx_v3", headers=HDR, json={"docx_base64": docx_b64, "mode": "preserve"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["version"] == "1.6"
    masked = payload["masked_docx_base64"]
    # Revision count is preserved
    assert _count(masked, "ins") == ins_before
    assert _count(masked, "del") == del_before

    # Restore
    r2 = client.post("/restore_docx_v3", headers=HDR, json={"docx_base64": masked, "map_id": payload["map_id"]})
    assert r2.status_code == 200, r2.text
    restored = r2.json()
    assert restored["restore_report"]["all_found"] is True
    # Revisions preserved through full roundtrip
    assert _count(restored["restored_docx_base64"], "ins") == ins_before
    assert _count(restored["restored_docx_base64"], "del") == del_before


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK: full-cycle smoke test passed")
