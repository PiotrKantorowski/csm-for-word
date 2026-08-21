import base64
import os
from pathlib import Path
from fastapi.testclient import TestClient

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"
from api import app  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)


def _fixture_docx_b64():
    from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # type: ignore
    return base64.b64encode(_build_docx_with_revisions()).decode("ascii")


def test_v4_prepare_restore_roundtrip_endpoint_exists_and_returns_files():
    original = _fixture_docx_b64()
    r = client.post("/v4/docx/prepare", headers=HDR, json={"docx_base64": original, "filename": "umowa.docx"})
    assert r.status_code == 200, r.text
    prepare = r.json()
    assert prepare["version"] == "1.6"
    assert prepare["map_id"]
    assert prepare["anon_docx_base64"]
    assert prepare["suggested_filename"].endswith("_CSM_anon.docx")
    assert prepare["negotiation_report"]["mutates_active_word_document"] is False
    assert prepare["negotiation_report"]["range_api_used"] is False

    r2 = client.post("/v4/docx/restore", headers=HDR, json={"docx_base64": prepare["anon_docx_base64"], "filename": prepare["suggested_filename"], "map_id": prepare["map_id"]})
    assert r2.status_code == 200, r2.text
    restored = r2.json()
    assert restored["version"] == "1.6"
    assert restored["restored_docx_base64"]
    assert restored["suggested_filename"].endswith("_CSM_jawny.docx")
    assert restored["restore_report"]["leftover_total_after_restore"] == 0

    r3 = client.post("/v4/docx/validate-roundtrip", headers=HDR, json={"original_docx_base64": original, "restored_docx_base64": restored["restored_docx_base64"]})
    assert r3.status_code == 200, r3.text
    assert "roundtrip" in r3.json()


def test_installer_artifacts_are_present_and_register_word_catalog():
    assert (ROOT / "ZAINSTALUJ_CSM.cmd").exists()
    assert (ROOT / "tools" / "install-csm.ps1").exists()
    assert (ROOT / "tools" / "repair-csm.ps1").exists()
    assert (ROOT / "tools" / "uninstall-csm.ps1").exists()
    # User-facing package exposes one installer at root; maintenance scripts live under tools.
    assert not (ROOT / "install-csm.ps1").exists()
    assert not (ROOT / "NAPRAW_CSM.cmd").exists()
    assert not (ROOT / "ODINSTALUJ_CSM.cmd").exists()
    wrapper = (ROOT / "ZAINSTALUJ_CSM.cmd").read_text(encoding="utf-8")
    assert "tools\\install-csm.ps1" in wrapper
    install = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    assert "C:\\CSM" in install
    assert "Invoke-ElevatedPhase" in install
    assert "-Verb RunAs" in install
    assert "-Wait -PassThru" in install
    # RC18: desktop shortcut removed from install flow; create-desktop-shortcut.ps1
    # is kept but no longer called automatically (replaced by Word taskpane panel).
    # assert "DesktopPath $OriginalDesktop" in install  # removed in rc18
    assert "ClaudeSafeModeAddin" in install
    assert "TrustedCatalogs" in install
    assert "Flags" in install
    assert "Clear-OfficeCache" in install


def test_taskpane_exposes_v4_file_workflow():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "CSM — anonimizacja dokumentu" in html
    assert "btnV4Prepare" in html
    assert "btnV4Restore" in html
    assert "/v4/current/prepare" in js
    assert "/v4/current/restore" in js
    assert "Oryginał nie został zmieniony" in js
    assert "v4RestoreFile" not in html
    assert "Utwórz zanonimizowaną kopię" in html
