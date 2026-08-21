"""API tests for /mask_docx_v3 and /restore_docx_v3."""
from __future__ import annotations

import base64
import os
import sys
import zipfile
import io
from pathlib import Path

from lxml import etree
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"

from api import app  # noqa: E402
from test_tracked_changes_preserve_mode import _build_docx_with_revisions, W  # noqa: E402

client = TestClient(app)
HDR = {"X-CSM-Token": "test-token"}


def _count(docx_b64: str, local: str) -> int:
    data = base64.b64decode(docx_b64)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        tree = etree.fromstring(zf.read("word/document.xml"))
    return len(tree.findall(f".//{W}{local}"))


def test_v3_mask_restore_endpoints_preserve_revision_counts():
    docx = _build_docx_with_revisions()
    docx_b64 = base64.b64encode(docx).decode("ascii")
    ins_before = _count(docx_b64, "ins")
    del_before = _count(docx_b64, "del")

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["version"] == "1.6"

    r = client.post("/mask_docx_v3", headers=HDR, json={"docx_base64": docx_b64, "mode": "preserve"})
    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["version"] == "1.6"
    assert payload["engine_version"] == "0.3.2-tc-placeholder-position-rebuild"
    assert payload["entities_count"] >= 3
    assert _count(payload["masked_docx_base64"], "ins") == ins_before
    assert _count(payload["masked_docx_base64"], "del") == del_before

    r2 = client.post("/restore_docx_v3", headers=HDR, json={"docx_base64": payload["masked_docx_base64"], "map_id": payload["map_id"]})
    assert r2.status_code == 200, r2.text
    restored = r2.json()
    assert restored["engine_version"] == "0.3.2-tc-placeholder-position-rebuild"
    assert restored["restore_report"]["all_found"] is True
    assert _count(restored["restored_docx_base64"], "ins") == ins_before
    assert _count(restored["restored_docx_base64"], "del") == del_before



def test_v3_mask_endpoint_accept_and_reject_modes_return_no_revisions():
    from test_tracked_changes_accept_mode import _build_docx_with_accept_reject_revisions
    docx_b64 = base64.b64encode(_build_docx_with_accept_reject_revisions()).decode("ascii")
    for mode in ("accept_then_mask", "reject_then_mask"):
        r = client.post("/mask_docx_v3", headers=HDR, json={"docx_base64": docx_b64, "mode": mode})
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["version"] == "1.6"
        assert _count(payload["masked_docx_base64"], "ins") == 0
        assert _count(payload["masked_docx_base64"], "del") == 0


def run_all():
    test_v3_mask_restore_endpoints_preserve_revision_counts()
    test_v3_mask_endpoint_accept_and_reject_modes_return_no_revisions()
    print("OK: v3 endpoint tests passed")


if __name__ == "__main__":
    run_all()
