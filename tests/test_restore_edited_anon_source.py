import base64
import io
import os
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["CSM_API_TOKEN"] = "test-token"
os.environ["CSM_DISABLE_OPEN_FILE"] = "1"

import api as api_module  # noqa: E402
from api import app, _docx_visible_text_for_change_detection  # noqa: E402
from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _docx_replace(data: bytes, old: str, new: str) -> bytes:
    src = io.BytesIO(data)
    out = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                raw = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    text = raw.decode("utf-8")
                    assert old in text
                    raw = text.replace(old, new).encode("utf-8")
                zout.writestr(info, raw)
    return out.getvalue()


def test_session_restore_prefers_open_word_live_copy_and_restores_edited_anon(monkeypatch):
    """When the taskpane is still attached to the original document, session
    restore must still use the open *_CSM_anon.docx if Word can SaveCopyAs it.

    This is the regression for: jawny DOCX was created, but without the user's
    edits, because CSM restored the untouched session baseline from disk.
    """
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "edycja-live.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_path = Path(prepared["anon_path"]).resolve()
    anon_bytes = anon_path.read_bytes()

    payload = api_module.load_map(prepared["map_id"])
    person_1 = next(r["original"] for r in payload["replacements"] if r["placeholder"] == "[OSOBA_1]")
    edited_anon = _docx_replace(
        anon_bytes,
        " podpisał dokument.",
        " podpisał dokument. Dodano warunek dla [OSOBA_1].",
    )

    def fake_live_copy(path):
        assert Path(path).resolve() == anon_path
        return edited_anon, None

    def disk_read_must_not_be_used(self):
        if self.resolve() == anon_path:
            raise AssertionError("session restore read the stale disk baseline instead of the Word live copy")
        return real_read_bytes(self)

    real_read_bytes = Path.read_bytes
    monkeypatch.setattr(api_module, "_read_open_word_document_copy", fake_live_copy)
    monkeypatch.setattr(Path, "read_bytes", disk_read_must_not_be_used)

    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": str(anon_path),
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
            "require_changes": True,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert restored["negotiation_report"]["restore_source"] == "word-com-savecopyas"
    restored_text = _docx_visible_text_for_change_detection(Path(restored["restored_path"]).read_bytes())
    assert "Dodano warunek dla" in restored_text
    assert person_1 in restored_text
    assert "[OSOBA_1]" not in restored_text


def test_automatic_session_restore_rejects_unchanged_baseline_when_changes_are_required(monkeypatch):
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "bez-zmian.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

    monkeypatch.setattr(api_module, "_read_open_word_document_copy", lambda path: (None, "not open in Word"))
    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": prepared["anon_path"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
            "require_changes": True,
        },
    )
    assert restore_response.status_code == 409, restore_response.text
    assert "bez zmian" in restore_response.text or "nie zostały zapisane" in restore_response.text


def test_taskpane_marks_automatic_session_restore_as_requiring_changes():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "require_changes: Boolean(options.requireChanges)" in js
    assert "restoreFromLastSavedAnonPath({ requireChanges: true" in js


def test_current_status_recognizes_metadata_stripped_anon_by_placeholders():
    """Regression for Word/SaveAs stripping CSM customXml metadata.

    The uploaded reproduction has no CSM metadata but visibly contains CSM
    placeholders and user edits. The taskpane must therefore classify the active
    package as anon using the current map, otherwise it falls back to the stale
    session baseline and raises HTTP 409.
    """
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "metadata-stripped.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_bytes = Path(prepared["anon_path"]).read_bytes()
    stripped = api_module._docx_remove_csm_metadata(anon_bytes)
    assert api_module._extract_csm_metadata(stripped) == {}

    status_response = client.post(
        "/v4/current/status",
        headers=HDR,
        json={"docx_base64": _b64(stripped), "map_id": prepared["map_id"]},
    )
    assert status_response.status_code == 200, status_response.text
    status = status_response.json()
    assert status["document_kind"] == "anon"
    assert status["metadata_missing_but_placeholder_match"] is True
    assert status["placeholder_match_map_id"] == prepared["map_id"]


def test_current_restore_uses_metadata_stripped_active_anon_and_preserves_edits():
    """An edited anon DOCX without CSM metadata must be restored from the active
    Office.js package, not rejected into the stale-session fallback.
    """
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "edited-no-metadata.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_bytes = Path(prepared["anon_path"]).read_bytes()
    edited = _docx_replace(
        anon_bytes,
        " podpisał dokument.",
        " podpisał dokument. Dodano nowy akapit dla [OSOBA_1].",
    )
    edited_no_meta = api_module._docx_remove_csm_metadata(edited)

    restore_response = client.post(
        "/v4/current/restore",
        headers=HDR,
        json={
            "docx_base64": _b64(edited_no_meta),
            "filename": "edited-no-metadata_CSM_anon.docx",
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    text = _docx_visible_text_for_change_detection(Path(restored["restored_path"]).read_bytes())
    payload = api_module.load_map(prepared["map_id"])
    person_1 = next(r["original"] for r in payload["replacements"] if r["placeholder"] == "[OSOBA_1]")
    assert "Dodano nowy akapit dla" in text
    assert person_1 in text
    assert "[OSOBA_1]" not in text


def test_taskpane_current_restore_status_passes_map_id_for_metadata_stripped_anon():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert 'apiPost("/v4/current/status", { docx_base64: docxBase64, map_id: expectedMap || undefined })' in js
    assert "metadata_missing_but_placeholder_match" in (ROOT / "server" / "api.py").read_text(encoding="utf-8")
