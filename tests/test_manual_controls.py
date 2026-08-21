import base64
import os
import sys
import zipfile
import io
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


def _texts(docx_b64):
    raw = base64.b64decode(docx_b64)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    return xml


def test_v042_map_preview_and_manual_remask_controls():
    original = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    r = client.post("/v4/current/prepare", headers=HDR, json={"docx_base64": original, "filename": "umowa.docx", "open_file": False})
    assert r.status_code == 200, r.text
    prepared = r.json()
    assert prepared["version"] == "1.6"
    assert prepared["map_id"]

    preview = client.post("/v4/map/preview", headers=HDR, json={"map_id": prepared["map_id"]})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["replacements"]
    assert {"category", "original", "placeholder", "count"}.issubset(body["replacements"][0].keys())

    remask = client.post(
        "/v4/current/remask-session",
        headers=HDR,
        json={
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "filename": "umowa.docx",
            "open_file": False,
            "controls": {"always": [{"value": "podpisał dokument", "category": "MANUAL_TEST"}], "never": ["Jan Kowalski"]},
        },
    )
    assert remask.status_code == 200, remask.text
    data = remask.json()
    assert data["version"] == "1.6"
    assert data["controls_applied"] is True
    assert data["map_id"] != prepared["map_id"]

    preview2 = client.post("/v4/map/preview", headers=HDR, json={"map_id": data["map_id"]}).json()
    assert any(r["category"] == "MANUAL_TEST" for r in preview2["replacements"])
    assert all(r["original"] != "Jan Kowalski" for r in preview2["replacements"])
