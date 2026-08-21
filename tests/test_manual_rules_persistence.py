from pathlib import Path

from fastapi.testclient import TestClient

import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"
from api import app  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_taskpane_has_local_manual_rules_persistence_controls():
    html = read("addin/taskpane.html")
    js = read("addin/taskpane.js")

    assert "Własne reguły ukrywania danych" in html
    assert "Zawsze ukrywaj te dane" in html
    assert "Nie ukrywaj tych danych" in html
    for element_id in [
        "btnSaveManualControls",
        "btnLoadManualControls",
        "btnExportManualControls",
        "btnImportManualControls",
    ]:
        assert f'id="{element_id}"' in html
        assert f'bindButton("{element_id}"' in js

    assert "CSM_MANUAL_CONTROLS_V1" in js
    assert "function saveManualControlsPreset" in js
    assert "function loadManualControlsPreset" in js
    assert "function exportManualControlsPreset" in js
    assert "async function importManualControlsPreset" in js
    assert "writeManualControlsToPanel" in js
    assert "Reguły ręczne są zapisane wyłącznie lokalnie" in js


def test_current_prepare_returns_controls_summary_for_local_rules():
    import base64
    from test_tracked_changes_preserve_mode import _build_docx_with_revisions

    client = TestClient(app)
    original = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={
            "docx_base64": original,
            "filename": "umowa.docx",
            "open_file": False,
            "controls": {
                "always": [{"value": "podpisał dokument", "category": "MANUAL_TEST"}],
                "never": ["Jan Kowalski"],
                "category_overrides": {"AZL 000000": "IDCARD_PL"},
                "merge_placeholders": [{"source": "[OSOBA_8]", "target": "[OSOBA_3]"}],
            },
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["version"] == "1.6"
    assert data["controls_applied"] is True
    assert data["controls_summary"] == {
        "always": 1,
        "never": 1,
        "category_overrides": 1,
        "category_changes": 0,
        "merge_placeholders": 1,
        "total": 4,
    }


def test_manual_rules_are_described_as_local_not_cloud_or_ocr():
    notes = read("RELEASE-NOTES-v1.6.txt")
    text = notes + "\n" + read("README.md")
    assert "lokal" in text.lower()
    assert "chmur" not in notes.lower()
    assert "ocr" not in notes.lower()
