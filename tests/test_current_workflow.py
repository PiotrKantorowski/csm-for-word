import base64
import os
from pathlib import Path
from fastapi.testclient import TestClient

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"
from api import app, _extract_csm_metadata, base64_to_bytes, _docx_diff_summary  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)


def _fixture_docx_b64():
    from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # type: ignore
    return base64.b64encode(_build_docx_with_revisions()).decode("ascii")


def test_v4_current_prepare_and_restore_without_manual_file_selection():
    original = _fixture_docx_b64()
    r = client.post("/v4/current/prepare", headers=HDR, json={
        "docx_base64": original,
        "filename": "umowa.docx",
        "open_file": False,
    })
    assert r.status_code == 200, r.text
    prepare = r.json()
    assert prepare["version"] == "1.6"
    assert prepare["map_id"]
    assert prepare["session_id"] == prepare["map_id"]
    assert prepare["suggested_filename"].endswith("_CSM_anon.docx")
    assert prepare["opened_file"] is False
    assert Path(prepare["anon_path"]).exists()
    assert Path(prepare["original_path"]).exists()

    anon_bytes = Path(prepare["anon_path"]).read_bytes()
    metadata = _extract_csm_metadata(anon_bytes)
    assert metadata["map_id"] == prepare["map_id"]
    assert metadata["csm_document_kind"] == "anon"

    r2 = client.post("/v4/current/restore", headers=HDR, json={
        "docx_base64": base64.b64encode(anon_bytes).decode("ascii"),
        "filename": prepare["suggested_filename"],
        "open_file": False,
    })
    assert r2.status_code == 200, r2.text
    restored = r2.json()
    assert restored["version"] == "1.6"
    assert restored["map_id"] == prepare["map_id"]
    assert restored["suggested_filename"].endswith("_CSM_jawny.docx")
    assert Path(restored["restored_path"]).exists()
    assert restored["restore_report"]["leftover_total_after_restore"] == 0
    # Final jawny document should not contain CSM session metadata.
    restored_bytes = Path(restored["restored_path"]).read_bytes()
    assert _extract_csm_metadata(restored_bytes) == {}
    assert _docx_diff_summary(base64_to_bytes(original), restored_bytes)["identical"] is True


def test_v4_current_restore_rejects_non_csm_docx():
    original = _fixture_docx_b64()
    r = client.post("/v4/current/restore", headers=HDR, json={
        "docx_base64": original,
        "filename": "umowa.docx",
        "open_file": False,
    })
    assert r.status_code == 400
