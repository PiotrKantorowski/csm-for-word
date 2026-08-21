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
client = TestClient(app)


def test_map_preview_exposes_local_export_metadata():
    original = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    prepared = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False},
    )
    assert prepared.status_code == 200, prepared.text
    map_id = prepared.json()["map_id"]

    preview = client.post("/v4/map/preview", headers=HDR, json={"map_id": map_id})
    assert preview.status_code == 200, preview.text
    body = preview.json()

    assert body["version"] == "1.6"
    assert body["map_id"] == map_id
    assert body["replacements"]
    assert body["category_counts"]
    assert "wyłącznie lokalnie" in body["privacy_notice"]
    assert "always_anonymize" in body["controls_supported"]
    assert "never_anonymize" in body["controls_supported"]
    assert "category_override" in body["controls_supported"]
    assert "merge_placeholders" in body["controls_supported"]
    assert body["preview_generated_at"].endswith("Z")


def test_taskpane_has_mapping_export_controls():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")

    assert "Własne reguły ukrywania danych" in html
    assert 'id="btnCopyMappings"' in html
    assert 'id="btnDownloadMappings"' in html
    assert "function mappingPreviewToText" in js
    assert "function copyMappingPreview" in js
    assert "function downloadMappingPreview" in js
    assert 'bindButton("btnCopyMappings", copyMappingPreview)' in js
    assert 'bindButton("btnDownloadMappings", downloadMappingPreview)' in js


def test_package_lock_versions_match_package_json():
    import json

    for package_path, lock_path in [
        (ROOT / "package.json", ROOT / "package-lock.json"),
        (ROOT / "addin" / "package.json", ROOT / "addin" / "package-lock.json"),
    ]:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        assert lock["name"] == package["name"]
        assert lock["version"] == package["version"]
        assert lock["packages"][""]["name"] == package["name"]
        assert lock["packages"][""]["version"] == package["version"]
