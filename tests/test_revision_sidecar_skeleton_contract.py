from pathlib import Path
import base64
import io
import os
import sys
import textwrap
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402
from api import app  # noqa: E402
from revision_sidecar import SIDECAR_PROTOCOL_VERSION  # noqa: E402

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


def test_dotnet_revision_sidecar_skeleton_files_are_present():
    project = ROOT / "sidecar" / "CSM.RevisionSidecar" / "CSM.RevisionSidecar.csproj"
    program = ROOT / "sidecar" / "CSM.RevisionSidecar" / "Program.cs"
    readme = ROOT / "sidecar" / "CSM.RevisionSidecar" / "README.md"
    assert project.exists()
    assert program.exists()
    assert readme.exists()
    project_text = project.read_text(encoding="utf-8")
    program_text = program.read_text(encoding="utf-8")
    # CSM v0.6 targets .NET 8 LTS. Do not widen this to preview TFMs for a local machine.
    assert "<TargetFramework>net8.0</TargetFramework>" in project_text, project_text[:200]
    assert "const string ProtocolVersion = \"0.1\"" in program_text
    assert "tracked-replace" in program_text
    assert "openxml_powertools_engine_not_wired" in program_text
    assert "OpenXmlRegex" in readme.read_text(encoding="utf-8")


def test_tracked_replace_endpoint_returns_redacted_contract_without_execution(monkeypatch):
    monkeypatch.delenv("CSM_REVISION_SIDECAR_CMD", raising=False)
    docx = _minimal_docx_base64("Jan Kowalski podpisał dokument.")
    r = client.post(
        "/v2/revision/tracked-replace",
        headers=HDR,
        json={
            "docx_base64": docx,
            "map_id": "map-sidecar-1",
            "author": "CSM Test",
            "execute": False,
            "operations": [
                {
                    "anchor_id": "CSM_ANCHOR:1",
                    "original_text": "Jan Kowalski",
                    "replacement_text": "[OSOBA_1]",
                }
            ],
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["action"] == "tracked-replace"
    assert data["protocol_version"] == SIDECAR_PROTOCOL_VERSION
    assert data["execution"]["executed"] is False
    contract = data["request_contract"]
    assert contract["docx_base64_present"] is True
    assert "docx_base64" not in contract
    assert contract["input"]["operations_count"] == 1
    assert contract["strategy"]["source"] == "OpenXmlRegex.Replace(trackRevisions=true)"
    assert contract["map_id"] == "map-sidecar-1"


def test_tracked_replace_endpoint_rejects_empty_operations():
    r = client.post(
        "/v2/revision/tracked-replace",
        headers=HDR,
        json={"docx_base64": _minimal_docx_base64(), "operations": [], "execute": False},
    )
    assert r.status_code == 400


def test_sidecar_ok_false_is_treated_as_execution_failure(monkeypatch, tmp_path):
    fake = tmp_path / "fake_sidecar.py"
    fake.write_text(
        textwrap.dedent(
            f"""
            import json
            print(json.dumps({{
                "ok": False,
                "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                "action": "normalize",
                "status": "engine_not_implemented",
                "error_code": "openxml_powertools_engine_not_wired",
                "error": "not wired"
            }}))
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")
    r = client.post(
        "/v2/revision/normalize",
        headers=HDR,
        json={"docx_base64": _minimal_docx_base64(), "execute": True},
    )
    assert r.status_code == 502, r.text
    assert "Mechanizm zachowania śledzenia zmian" in r.text


def test_sidecar_success_without_result_docx_is_protocol_error(monkeypatch, tmp_path):
    fake = tmp_path / "fake_sidecar_success_without_docx.py"
    fake.write_text(
        textwrap.dedent(
            f"""
            import json
            print(json.dumps({{
                "ok": True,
                "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                "action": "normalize",
                "status": "completed"
            }}))
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")
    r = client.post(
        "/v2/revision/normalize",
        headers=HDR,
        json={"docx_base64": _minimal_docx_base64(), "execute": True},
    )
    assert r.status_code == 502, r.text
    assert "nieprawid" in r.text.lower() or "mechanizm zachowania śledzenia zmian" in r.text.lower()


def test_sidecar_success_with_invalid_result_docx_is_protocol_error(monkeypatch, tmp_path):
    fake = tmp_path / "fake_sidecar_success_invalid_docx.py"
    fake.write_text(
        textwrap.dedent(
            f"""
            import json
            print(json.dumps({{
                "ok": True,
                "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                "action": "normalize",
                "status": "completed",
                "docx_base64": "not-a-docx"
            }}))
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")
    r = client.post(
        "/v2/revision/normalize",
        headers=HDR,
        json={"docx_base64": _minimal_docx_base64(), "execute": True},
    )
    assert r.status_code == 502, r.text


def test_sidecar_success_with_valid_result_docx_is_accepted(monkeypatch, tmp_path):
    fake = tmp_path / "fake_sidecar_success_valid_docx.py"
    result_docx = _minimal_docx_base64("Sidecar output")
    fake.write_text(
        textwrap.dedent(
            f"""
            import json
            print(json.dumps({{
                "ok": True,
                "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                "action": "normalize",
                "status": "completed",
                "docx_base64": "{result_docx}"
            }}))
            """
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")
    r = client.post(
        "/v2/revision/normalize",
        headers=HDR,
        json={"docx_base64": _minimal_docx_base64(), "execute": True},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["execution"]["executed"] is True
    assert data["execution"]["status"] == "completed"
    assert data["result"]["docx_base64"] == result_docx
