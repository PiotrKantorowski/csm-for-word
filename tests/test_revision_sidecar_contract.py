from pathlib import Path
import base64
import io
import os
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402
from api import app  # noqa: E402
from revision_sidecar import (  # noqa: E402
    SIDECAR_PROTOCOL_VERSION,
    build_sidecar_request,
    sidecar_status_dict,
)

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)


def _minimal_docx_base64(text="Hello CSM"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/></Types>")
        zf.writestr("_rels/.rels", "<?xml version='1.0'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'></Relationships>")
        zf.writestr(
            "word/document.xml",
            "<?xml version='1.0' encoding='UTF-8'?><w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>"
            + text
            + "</w:t></w:r></w:p></w:body></w:document>",
        )
    return base64.b64encode(buf.getvalue()).decode("ascii")


def test_sidecar_status_reports_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("CSM_REVISION_SIDECAR_CMD", raising=False)
    status = sidecar_status_dict()
    assert status["available"] is False
    assert status["configured"] is False
    assert status["protocol_version"] == SIDECAR_PROTOCOL_VERSION

    r = client.get("/v2/revision/sidecar/status", headers=HDR)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["protocol_version"] == SIDECAR_PROTOCOL_VERSION
    assert data["sidecar_status"]["available"] is False
    assert "compare" in data["supported_actions"]
    assert "normalize" in data["supported_actions"]


def test_build_sidecar_request_adds_hashes_and_counts_without_losing_action():
    payload = build_sidecar_request(
        action="tracked-replace",
        docx_base64="abc",
        operations=[{"from_text": "A", "to_text": "B"}],
        author="CSM Test",
        map_id="map-1",
    )
    assert payload["action"] == "tracked-replace"
    assert payload["protocol_version"] == SIDECAR_PROTOCOL_VERSION
    assert payload["input"]["operations_count"] == 1
    assert payload["input"]["docx_base64_length"] == 3
    assert payload["input"]["docx_base64_sha256"]


def test_revision_compare_dry_run_returns_redacted_contract(monkeypatch):
    monkeypatch.delenv("CSM_REVISION_SIDECAR_CMD", raising=False)
    original = _minimal_docx_base64("Original")
    revised = _minimal_docx_base64("Revised")
    r = client.post(
        "/v2/revision/compare",
        headers=HDR,
        json={"original_docx_base64": original, "revised_docx_base64": revised, "author": "CSM", "execute": False},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["action"] == "compare"
    assert data["execution"]["executed"] is False
    assert data["execution"]["status"] == "dry_run"
    assert data["request_contract"]["docx_base64_present"] is True
    assert data["request_contract"]["revised_docx_base64_present"] is True
    assert "docx_base64" not in data["request_contract"]
    assert "revised_docx_base64" not in data["request_contract"]
    assert data["request_contract"]["input"]["docx_base64_sha256"]
    assert data["request_contract"]["strategy"]["source"] == "WmlComparer.Compare"


def test_revision_normalize_dry_run_returns_revision_processor_contract(monkeypatch):
    monkeypatch.delenv("CSM_REVISION_SIDECAR_CMD", raising=False)
    docx = _minimal_docx_base64("Normalize me")
    r = client.post(
        "/v2/revision/normalize",
        headers=HDR,
        json={"docx_base64": docx, "author": "CSM", "execute": False},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["action"] == "normalize"
    assert data["request_contract"]["strategy"]["source"] == "RevisionProcessor.AcceptReject"
    assert data["request_contract"]["docx_base64_present"] is True
    assert data["request_contract"]["revised_docx_base64_present"] is False


def test_revision_sidecar_execute_returns_503_when_not_configured(monkeypatch):
    monkeypatch.delenv("CSM_REVISION_SIDECAR_CMD", raising=False)
    docx = _minimal_docx_base64("Execute")
    r = client.post(
        "/v2/revision/normalize",
        headers=HDR,
        json={"docx_base64": docx, "execute": True},
    )
    assert r.status_code == 503, r.text
    assert "Mechanizm zachowania śledzenia zmian" in r.text


def test_revision_sidecar_endpoints_reject_invalid_docx_base64():
    r = client.post(
        "/v2/revision/normalize",
        headers=HDR,
        json={"docx_base64": "not-a-docx", "execute": False},
    )
    assert r.status_code == 400


def test_sidecar_status_requires_local_api_token():
    r = client.get("/v2/revision/sidecar/status")
    assert r.status_code == 401, r.text


def test_sidecar_status_redacts_configured_command(monkeypatch):
    secret_command = "/very/secret/CSM.RevisionSidecar.exe --config /tmp/private.json"
    monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", secret_command)
    r = client.get("/v2/revision/sidecar/status", headers=HDR)
    assert r.status_code == 200, r.text
    data = r.json()
    status = data["sidecar_status"]
    assert status["configured"] is True
    assert status["command"] == "<redacted>"
    assert status["command_configured"] is True
    assert "/very/secret" not in r.text
    assert "private.json" not in r.text


def test_sidecar_status_probe_reports_reachable_capabilities(monkeypatch, tmp_path):
    fake = tmp_path / "fake_status_sidecar.py"
    fake.write_text(
        """
import json, sys
req = json.load(sys.stdin)
print(json.dumps({
    "ok": True,
    "protocol_version": "0.1",
    "action": req.get("action", "status"),
    "status": "ready",
    "engine": "fake-status-sidecar",
    "supported_actions": ["status", "normalize", "compare", "tracked-replace"],
    "capabilities": {"normalize": True, "compare": True, "tracked-replace": True}
}))
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")

    r = client.get("/v2/revision/sidecar/status", headers=HDR)
    assert r.status_code == 200, r.text
    data = r.json()
    status = data["sidecar_status"]
    assert status["available"] is True
    assert status["reachable"] is True
    assert status["probe_status"] == "ok"
    assert status["engine"] == "fake-status-sidecar"
    assert status["capabilities"]["tracked-replace"] is True
    assert status["command"] == "<redacted>"
    assert status["executable"] == "<redacted>"
    assert str(fake) not in r.text


def test_sidecar_status_probe_failure_does_not_leak_command(monkeypatch, tmp_path):
    fake = tmp_path / "fake_bad_status_sidecar.py"
    fake.write_text(
        """
import json
print(json.dumps({"ok": True, "protocol_version": "9.9", "action": "status"}))
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")

    r = client.get("/v2/revision/sidecar/status", headers=HDR)
    assert r.status_code == 200, r.text
    status = r.json()["sidecar_status"]
    assert status["configured"] is True
    assert status["available"] is False
    assert status["reachable"] is False
    assert status["probe_status"] == "failed"
    assert status["command"] == "<redacted>"
    assert status["executable"] == "<redacted>"
    assert str(fake) not in r.text
    assert "Niezgodna wersja komunikacji technicznej" in status["reason"]
