"""
test_revision_sidecar_integration.py
=====================================
Integration test: Python API → sidecar → DOCX with w:ins / w:del.

Two test groups:
  A) Fake-sidecar tests (always runnable) — verify the Python API chain
     end-to-end using a scripted Python fake sidecar that returns a realistic
     DOCX containing w:ins and w:del markup.

  B) Real-sidecar smoke test (skipped unless CSM_REVISION_SIDECAR_CMD is set
     and points to the compiled .NET sidecar) — verifies that the real
     Clippit/OpenXmlPowerTools tracked-replace produces correct output.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import textwrap
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402
from api import app  # noqa: E402
from revision_sidecar import SIDECAR_PROTOCOL_VERSION  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_docx(text: str = "Hello CSM") -> str:
    """Return base64-encoded minimal DOCX containing *text*.

    Uses proper content-type Override and styles part so Clippit's WmlDocument
    constructor (which validates the package structure) accepts it.
    """
    ns_ct = "http://schemas.openxmlformats.org/package/2006/content-types"
    ns_rel = "http://schemas.openxmlformats.org/package/2006/relationships"
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            f"<Types xmlns='{ns_ct}'>"
            f"<Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/>"
            f"<Default Extension='xml' ContentType='application/xml'/>"
            f"<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
            f"<Override PartName='/word/styles.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml'/>"
            f"</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            f"<Relationships xmlns='{ns_rel}'>"
            f"<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument'"
            f" Target='word/document.xml'/></Relationships>",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            f"<Relationships xmlns='{ns_rel}'>"
            f"<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles'"
            f" Target='styles.xml'/></Relationships>",
        )
        zf.writestr(
            "word/styles.xml",
            f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            f"<w:styles xmlns:w='{ns_w}'>"
            f"<w:style w:type='paragraph' w:default='1' w:styleId='Normal'>"
            f"<w:name w:val='Normal'/></w:style>"
            f"</w:styles>",
        )
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        zf.writestr(
            "word/document.xml",
            f"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
            f"<w:document xmlns:w='{ns_w}'>"
            f"<w:body><w:p><w:r><w:t>{safe}</w:t></w:r></w:p><w:sectPr/></w:body></w:document>",
        )
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _docx_with_tracked_changes(original: str, replacement: str) -> str:
    """
    Return base64 DOCX that already contains w:del / w:ins markup for
    (original → replacement). Used by the fake sidecar to simulate a
    real tracked-replace result.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='xml' ContentType='application/xml'/></Types>",
        )
        zf.writestr(
            "_rels/.rels",
            "<?xml version='1.0'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument'"
            " Target='word/document.xml'/></Relationships>",
        )
        # Build document.xml with w:del and w:ins markup
        doc_xml = (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
            "<w:body><w:p>"
            "<w:del w:id='1' w:author='CSM' w:date='2025-01-01T00:00:00Z'>"
            f"<w:r><w:delText>{original}</w:delText></w:r>"
            "</w:del>"
            "<w:ins w:id='2' w:author='CSM' w:date='2025-01-01T00:00:00Z'>"
            f"<w:r><w:t>{replacement}</w:t></w:r>"
            "</w:ins>"
            "</w:p></w:body></w:document>"
        )
        zf.writestr("word/document.xml", doc_xml)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _is_valid_docx(b64: str) -> bool:
    try:
        raw = base64.b64decode(b64)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            return "word/document.xml" in zf.namelist()
    except Exception:
        return False


def _get_document_xml(b64: str) -> str:
    raw = base64.b64decode(b64)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        return zf.read("word/document.xml").decode("utf-8")


# ===========================================================================
# Group A: Fake-sidecar tests (always run)
# ===========================================================================

class TestTrackedReplaceWithFakeSidecar:
    """
    Validates the full Python API chain:
    client → POST /v2/revision/tracked-replace (execute=True)
           → Python builds payload
           → invokes fake sidecar subprocess
           → validates returned DOCX
           → returns 200 with result.docx_base64
    """

    def test_tracked_replace_execute_true_returns_200_with_docx(self, monkeypatch, tmp_path):
        """
        Full chain: API → fake sidecar → 200 with valid DOCX base64.
        """
        result_docx = _docx_with_tracked_changes("Jan Kowalski", "[[CSM_PERSON_1]]")

        fake = tmp_path / "fake_sidecar.py"
        fake.write_text(
            textwrap.dedent(f"""\
                import json, sys
                req = json.load(sys.stdin)
                print(json.dumps({{
                    "ok": True,
                    "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                    "action": req.get("action", "tracked-replace"),
                    "status": "completed",
                    "engine": "fake-sidecar",
                    "docx_base64": "{result_docx}",
                    "metadata": {{"engine": "fake", "revision_count": 1}}
                }}))
            """),
            encoding="utf-8",
        )
        monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")

        docx = _minimal_docx("Jan Kowalski podpisał umowę.")
        r = client.post(
            "/v2/revision/tracked-replace",
            headers=HDR,
            json={
                "docx_base64": docx,
                "map_id": "map-iter9-1",
                "author": "CSM",
                "execute": True,
                "operations": [
                    {
                        "anchor_id": "CSM_ANCHOR:1",
                        "original_text": "Jan Kowalski",
                        "replacement_text": "[[CSM_PERSON_1]]",
                    }
                ],
            },
        )

        assert r.status_code == 200, r.text
        data = r.json()
        assert data["action"] == "tracked-replace"
        assert data["execution"]["executed"] is True
        assert data["execution"]["status"] == "completed"

        result_b64 = data["result"]["docx_base64"]
        assert _is_valid_docx(result_b64), "result docx_base64 is not a valid DOCX"

    def test_result_docx_contains_w_ins_and_w_del(self, monkeypatch, tmp_path):
        """
        The result DOCX from tracked-replace must contain w:ins and w:del.
        """
        result_docx = _docx_with_tracked_changes("Jan Kowalski", "[[CSM_PERSON_1]]")

        fake = tmp_path / "fake_sidecar_insdel.py"
        fake.write_text(
            textwrap.dedent(f"""\
                import json, sys
                req = json.load(sys.stdin)
                print(json.dumps({{
                    "ok": True,
                    "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                    "action": "tracked-replace",
                    "status": "completed",
                    "docx_base64": "{result_docx}"
                }}))
            """),
            encoding="utf-8",
        )
        monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")

        docx = _minimal_docx("Jan Kowalski")
        r = client.post(
            "/v2/revision/tracked-replace",
            headers=HDR,
            json={
                "docx_base64": docx,
                "execute": True,
                "operations": [{"original_text": "Jan Kowalski", "replacement_text": "[[P1]]"}],
            },
        )
        assert r.status_code == 200, r.text
        xml = _get_document_xml(r.json()["result"]["docx_base64"])
        assert "w:ins" in xml, "Expected w:ins in result document.xml"
        assert "w:del" in xml, "Expected w:del in result document.xml"

    def test_result_docx_zip_contains_word_document_xml(self, monkeypatch, tmp_path):
        """
        After tracked-replace the result DOCX must be a valid ZIP with word/document.xml.
        """
        result_docx = _docx_with_tracked_changes("foo", "bar")

        fake = tmp_path / "fake_valid.py"
        fake.write_text(
            textwrap.dedent(f"""\
                import json, sys
                req = json.load(sys.stdin)
                print(json.dumps({{
                    "ok": True,
                    "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                    "action": "tracked-replace",
                    "status": "completed",
                    "docx_base64": "{result_docx}"
                }}))
            """),
            encoding="utf-8",
        )
        monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")

        r = client.post(
            "/v2/revision/tracked-replace",
            headers=HDR,
            json={
                "docx_base64": _minimal_docx("foo bar"),
                "execute": True,
                "operations": [{"original_text": "foo", "replacement_text": "bar"}],
            },
        )
        assert r.status_code == 200, r.text
        b64 = r.json()["result"]["docx_base64"]
        raw = base64.b64decode(b64)
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            assert "word/document.xml" in zf.namelist()

    def test_normalize_execute_true_returns_200_with_docx(self, monkeypatch, tmp_path):
        """normalize with execute=True and valid fake sidecar → 200."""
        result_docx = _minimal_docx("normalized")
        fake = tmp_path / "fake_norm.py"
        fake.write_text(
            textwrap.dedent(f"""\
                import json, sys
                req = json.load(sys.stdin)
                print(json.dumps({{
                    "ok": True,
                    "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                    "action": "normalize",
                    "status": "completed",
                    "docx_base64": "{result_docx}"
                }}))
            """),
            encoding="utf-8",
        )
        monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")
        r = client.post(
            "/v2/revision/normalize",
            headers=HDR,
            json={"docx_base64": _minimal_docx("original"), "execute": True},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["execution"]["executed"] is True
        assert _is_valid_docx(data["result"]["docx_base64"])

    def test_compare_execute_true_returns_200_with_docx(self, monkeypatch, tmp_path):
        """compare with execute=True and valid fake sidecar → 200."""
        result_docx = _docx_with_tracked_changes("Original", "Revised")
        fake = tmp_path / "fake_cmp.py"
        fake.write_text(
            textwrap.dedent(f"""\
                import json, sys
                req = json.load(sys.stdin)
                print(json.dumps({{
                    "ok": True,
                    "protocol_version": "{SIDECAR_PROTOCOL_VERSION}",
                    "action": "compare",
                    "status": "completed",
                    "docx_base64": "{result_docx}"
                }}))
            """),
            encoding="utf-8",
        )
        monkeypatch.setenv("CSM_REVISION_SIDECAR_CMD", f"{sys.executable} {fake}")
        r = client.post(
            "/v2/revision/compare",
            headers=HDR,
            json={
                "original_docx_base64": _minimal_docx("Original text."),
                "revised_docx_base64":  _minimal_docx("Revised text."),
                "author": "CSM",
                "execute": True,
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["execution"]["executed"] is True
        assert _is_valid_docx(data["result"]["docx_base64"])


# ===========================================================================
# Group B: Real sidecar smoke test (skipped unless sidecar is compiled)
# ===========================================================================

_REAL_SIDECAR_CMD = os.environ.get("CSM_REVISION_SIDECAR_CMD", "").strip()
_REAL_SIDECAR_AVAILABLE = bool(_REAL_SIDECAR_CMD)


@pytest.mark.skipif(
    not _REAL_SIDECAR_AVAILABLE,
    reason="CSM_REVISION_SIDECAR_CMD not set — real sidecar not compiled. "
           "Set env var to compiled sidecar and re-run.",
)
class TestTrackedReplaceWithRealSidecar:
    """
    End-to-end smoke test using the compiled .NET sidecar.
    Requires:
      $env:CSM_REVISION_SIDECAR_CMD = "dotnet sidecar/CSM.RevisionSidecar/bin/Release/net8.0/CSM.RevisionSidecar.dll"
    """

    def test_tracked_replace_real_sidecar_returns_200(self):
        docx = _minimal_docx("Jan Kowalski podpisał umowę najmu.")
        r = client.post(
            "/v2/revision/tracked-replace",
            headers=HDR,
            json={
                "docx_base64": docx,
                "author": "CSM",
                "execute": True,
                "operations": [
                    {
                        "anchor_id": "CSM_ANCHOR:1",
                        "original_text": "Jan Kowalski",
                        "replacement_text": "[[CSM_PERSON_1]]",
                    }
                ],
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["execution"]["executed"] is True
        b64 = data["result"]["docx_base64"]
        assert _is_valid_docx(b64)
        xml = _get_document_xml(b64)
        assert "w:ins" in xml, "Real sidecar must produce w:ins"
        assert "w:del" in xml, "Real sidecar must produce w:del"

    def test_normalize_real_sidecar_returns_200(self):
        docx = _minimal_docx("Tekst do normalizacji.")
        r = client.post(
            "/v2/revision/normalize",
            headers=HDR,
            json={"docx_base64": docx, "execute": True},
        )
        assert r.status_code == 200, r.text
        assert _is_valid_docx(r.json()["result"]["docx_base64"])

    def test_compare_real_sidecar_returns_200(self):
        r = client.post(
            "/v2/revision/compare",
            headers=HDR,
            json={
                "original_docx_base64": _minimal_docx("Original sentence."),
                "revised_docx_base64":  _minimal_docx("Revised sentence."),
                "author": "CSM",
                "execute": True,
            },
        )
        assert r.status_code == 200, r.text
        assert _is_valid_docx(r.json()["result"]["docx_base64"])
