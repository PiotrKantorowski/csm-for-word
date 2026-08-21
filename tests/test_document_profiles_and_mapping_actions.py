import base64
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["CSM_API_TOKEN"] = "test-token"

from api import app  # noqa: E402
from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_taskpane_has_document_profiles_and_quick_mapping_actions():
    html = read("addin/taskpane.html")
    js = read("addin/taskpane.js")

    assert 'id="documentProfile"' in html
    assert 'value="pleadings"' in html
    assert 'Pisma procesowe' in html
    assert 'value="contracts"' in html
    assert 'Umowy' in html
    assert 'function selectedDocumentProfile' in js
    assert 'function renderMappingActions' in js
    assert 'data-map-action="never"' in js
    assert 'data-map-action="always"' in js
    assert 'data-map-action="category"' in js
    assert "Zmień typ" in js
    assert 'data-map-action="merge"' in js
    assert "Scal z..." in js
    assert 'addManualRuleFromMapping' in js


def test_current_prepare_accepts_profiles_and_returns_profile_report():
    client = TestClient(app)
    original = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False, "document_profile": "contracts"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["version"] == "1.6"
    assert data["document_profile"] == "contracts"
    report = data["anonymization_report"]
    assert report["document_profile"]["id"] == "contracts"
    assert report["document_profile"]["label"] == "Umowy"
    assert "BANK_ACCOUNT" in report["document_profile"]["priority_categories"]


def test_map_preview_exposes_profile_catalog_and_selected_profile():
    client = TestClient(app)
    original = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    prepared = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "pozew.docx", "open_file": False, "document_profile": "pleadings"},
    )
    assert prepared.status_code == 200, prepared.text
    map_id = prepared.json()["map_id"]

    preview = client.post("/v4/map/preview", headers=HDR, json={"map_id": map_id, "document_profile": "pleadings"})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    ids = {p["id"] for p in body["document_profiles"]}
    assert {"auto", "pleadings", "contracts"}.issubset(ids)
    assert body["selected_profile"]["id"] == "pleadings"
    assert body["selected_profile"]["label"] == "Pisma procesowe"
    assert "SYGNATURA" in body["selected_profile"]["priority_categories"]
    assert "document_profiles" in body["controls_supported"]


def test_v050_final_mapping_actions_are_guided_not_self_referential():
    js = read("addin/taskpane.js")
    assert "function promptForManualCategory" in js
    assert "function promptForMergeTarget" in js
    assert "MANUAL_CATEGORY_OPTIONS" in js
    assert "mappingPreviewPlaceholders" in js
    assert "Nie dodano scalania placeholdera samego do siebie" in js
    assert "appendLineToTextarea(\"manualMerge\", `${rawPlaceholder} => ${rawPlaceholder}`)" not in js
    assert "WYBIERZ_PLACEHOLDER_DOCELOWY" not in js
    assert "WYBIERZ_KATEGORIĘ" not in js


def test_current_release_uses_csm_brand_assets():
    html = read("addin/taskpane.html")
    assert "assets/logo-csm-primary.png" in html
    assert "logo-csm-monochrome-v050.png" not in html
    assert "logo-prawo-dla-biznesu.png" not in html
    assert "logo-kxg.png" not in html
    for rel in [
        "addin/assets/logo-csm-primary.png",
        "addin/assets/logo-csm-primary-v050.png",
        "addin/assets/logo-csm-primary-final2.png",
        "addin/assets/logo-csm-monochrome.png",
        "addin/assets/logo-csm-app.png",
        "addin/assets/logo-csm-app-v050.png",
        "assets/logo-csm-primary.png",
        "assets/logo-csm-primary-v050.png",
        "assets/logo-csm-primary-final2.png",
        "assets/logo-csm-monochrome.png",
        "assets/logo-csm-app.png",
        "assets/logo-csm-app-v050.png",
        "addin/icon-16.png",
        "addin/icon-16-csm-v050.png",
        "addin/icon-16-csm-final2.png",
        "addin/icon-32.png",
        "addin/icon-32-csm-v050.png",
        "addin/icon-32-csm-final2.png",
        "addin/icon-64.png",
        "addin/icon-64-csm-v050.png",
        "addin/icon-64-csm-final2.png",
        "addin/icon-80.png",
        "addin/icon-80-csm-v050.png",
        "addin/icon-80-csm-final2.png",
        "assets/csm.ico",
        "addin/assets/csm.ico",
    ]:
        assert (ROOT / rel).exists(), rel
