import base64
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["CSM_API_TOKEN"] = "test-token"
os.environ["CSM_DISABLE_OPEN_FILE"] = "1"

from api import app, _docx_diff_summary, _safe_original_docx_target, _sessions_dir, base64_to_bytes  # noqa: E402
from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_v4_session_restore_last_uses_saved_anon_file_not_active_word_context():
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

    # Simulates Word taskpane still bound to the original document: no active
    # DOCX package is sent. Restore must use the saved *_CSM_anon.docx path.
    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": prepared["anon_path"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert restored["map_id"] == prepared["map_id"]
    assert Path(restored["restored_path"]).exists()
    restored_bytes = Path(restored["restored_path"]).read_bytes()
    assert _docx_diff_summary(base64_to_bytes(original), restored_bytes)["identical"] is True


def test_v4_session_restore_last_rejects_original_path_even_with_map_id():
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": prepared["original_path"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 400
    assert "_CSM_anon.docx" in restore_response.text


def test_frontend_restore_prefers_verified_active_anon_package_then_falls_back_to_saved_session():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    restore = js[js.index("async function v4RestoreDocxCopy"):js.index("async function v4RestoreManualDocxCopy")]
    current_helper = js[js.index("async function tryRestoreFromCurrentAnonPackage"):js.index("async function v4RestoreDocxCopy")]
    assert 'apiPostHeavy("/v4/session/restore-last"' in js or 'apiPost("/v4/session/restore-last"' in js
    assert "restoreFromLastSavedAnonPath" in restore
    assert "tryRestoreFromCurrentAnonPackage" in restore
    assert 'apiPostHeavy("/v4/current/status"' in current_helper or 'apiPost("/v4/current/status"' in current_helper
    assert 'apiPostHeavy("/v4/current/restore"' in current_helper or 'apiPost("/v4/current/restore"' in current_helper
    assert 'kind !== "anon"' in current_helper
    assert "falls back to the saved" in restore
    assert "zapisz go najpierw (Ctrl+S)" in restore


def test_frontend_session_restore_fallback_is_guarded_against_stale_sessions():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "function canUseLastSavedAnonFallback" in js
    assert "V4_LAST_SOURCE_FILENAME_KEY" in js
    assert "V4_LAST_PREPARED_AT_KEY" in js
    assert "currentNorm !== sourceNorm" in js
    assert "Żeby nie przywrócić danych z innej sprawy" in js
    assert "lastPrepareAgeMs" in js
    assert "rememberV4SourceContext(filename" in js


def test_restore_target_rejects_csm_working_paths():
    session_target, session_reason = _safe_original_docx_target(str(_sessions_dir() / "s-test" / "umowa_CSM_anon.docx"))
    assert session_target is None
    assert "roboczy CSM" in session_reason or "sesji" in session_reason

    restored_target, restored_reason = _safe_original_docx_target(str(Path.home() / "umowa_CSM_jawny.docx"))
    assert restored_target is None
    assert "roboczy CSM" in restored_reason

    original_target, original_reason = _safe_original_docx_target(str(Path.home() / "umowa.docx"))
    assert original_target is not None
    assert original_reason is None


def test_frontend_captures_word_paths_before_async_focus_changes():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    prepare = js[js.index("async function v4PrepareDocxCopy"):js.index("async function preRestoreRevisionAwareRangePass")]
    restore = js[js.index("async function v4RestoreDocxCopy"):js.index("async function v4RestoreManualDocxCopy")]
    assert "function officeUrlToLocalPath" in js
    assert "getFilePropertiesAsync" in js
    assert "file://server/share/doc.docx" in js
    assert prepare.index("currentDocumentFullPathAsync") < prepare.index('requireDocumentKindForV4("original", "prepare")')
    assert restore.index("currentDocumentFullPathAsync") < restore.index("ensureServerReadyForOperation")


def test_v4_session_restore_last_does_not_rewrite_open_anon_file(monkeypatch):
    """Regression for Windows Word lock: restoring from saved *_CSM_anon.docx
    must not write back to the same file. Word can hold that file open and deny
    overwrite access, which previously surfaced as HTTP 400 / Errno 13.
    """
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "blokada.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    locked_anon = Path(prepared["anon_path"]).resolve()

    real_write_bytes = Path.write_bytes

    def guarded_write_bytes(self, data):
        if self.resolve() == locked_anon:
            raise PermissionError(13, "Permission denied", str(self))
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": str(locked_anon),
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert Path(restored["anon_path"]).resolve() == locked_anon
    assert Path(restored["restored_path"]).exists()
    assert restored["restored_path"].endswith("_CSM_jawny.docx")


def test_v4_session_restore_last_creates_unique_jawny_when_previous_is_open(monkeypatch):
    """Repeated restore should not overwrite an already open jawny document."""
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "powtorka.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

    first = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": prepared["anon_path"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert first.status_code == 200, first.text
    first_restored = Path(first.json()["restored_path"]).resolve()
    assert first_restored.exists()

    real_write_bytes = Path.write_bytes

    def guarded_write_bytes(self, data):
        if self.resolve() == first_restored:
            raise PermissionError(13, "Permission denied", str(self))
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    second = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": prepared["anon_path"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert second.status_code == 200, second.text
    second_restored = Path(second.json()["restored_path"]).resolve()
    assert second_restored.exists()
    assert second_restored != first_restored
    assert second_restored.name.startswith("powtorka_CSM_jawny_")


def test_v4_session_restore_last_retries_transient_anon_read_lock(monkeypatch):
    """If Word briefly locks *_CSM_anon.docx during save/open, restore should retry
    rather than failing immediately with HTTP 400 / Errno 13.
    """
    monkeypatch.setenv("CSM_FAST_LOCK_RETRY", "1")
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "chwilowa-blokada.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    locked_anon = Path(prepared["anon_path"]).resolve()

    real_read_bytes = Path.read_bytes
    calls = {"n": 0}

    def guarded_read_bytes(self):
        if self.resolve() == locked_anon and calls["n"] < 2:
            calls["n"] += 1
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": str(locked_anon),
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    assert calls["n"] == 2
    assert Path(restore_response.json()["restored_path"]).exists()


def test_v4_session_restore_last_reports_persistent_anon_read_lock_as_actionable_423(monkeypatch):
    """A persistent Word lock should produce a clear retry/save message, not an
    opaque redacted PermissionError path.
    """
    monkeypatch.setenv("CSM_FAST_LOCK_RETRY", "1")
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "stala-blokada.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    locked_anon = Path(prepared["anon_path"]).resolve()

    real_read_bytes = Path.read_bytes

    def guarded_read_bytes(self):
        if self.resolve() == locked_anon:
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": str(locked_anon),
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 423, restore_response.text
    assert "Ctrl+S" in restore_response.text
    assert "Permission denied" not in restore_response.text


def test_v4_restore_report_write_failure_is_nonfatal(monkeypatch):
    """Creation of the jawny DOCX is more important than a diagnostic JSON report.
    A locked report_restore.json must not turn a successful restore into HTTP 400.
    """
    import api as api_module

    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "raport-lock.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

    real_write_json = api_module._write_json

    def guarded_write_json(path, data):
        if Path(path).name == "report_restore.json":
            raise PermissionError(13, "Permission denied", str(path))
        return real_write_json(path, data)

    monkeypatch.setattr(api_module, "_write_json", guarded_write_json)
    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": prepared["anon_path"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert Path(restored["restored_path"]).exists()
    assert any("raportu technicznego" in w for w in restored.get("warnings", []))


def test_v4_session_restore_last_retries_locked_first_jawny_candidate(monkeypatch):
    """If the default jawny output path is denied, CSM should generate another
    filename instead of failing the restore.
    """
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "jawny-candidate-lock.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    session_dir = Path(prepared["anon_path"]).resolve().parent
    default_jawny = session_dir / "jawny-candidate-lock_CSM_jawny.docx"

    real_write_bytes = Path.write_bytes
    calls = {"blocked": 0}

    def guarded_write_bytes(self, data):
        if self.resolve() == default_jawny.resolve() and calls["blocked"] < 1:
            calls["blocked"] += 1
            raise PermissionError(13, "Permission denied", str(self))
        return real_write_bytes(self, data)

    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    restore_response = client.post(
        "/v4/session/restore-last",
        headers=HDR,
        json={
            "anon_path": prepared["anon_path"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored_path = Path(restore_response.json()["restored_path"]).resolve()
    assert calls["blocked"] == 1
    assert restored_path.exists()
    assert restored_path != default_jawny.resolve()


def _append_docx_paragraph(docx_bytes: bytes, text: str) -> bytes:
    """Append a simple Word paragraph to word/document.xml in a DOCX package."""
    import html
    import io
    import zipfile

    out = io.BytesIO()
    paragraph = f'<w:p><w:r><w:t>{html.escape(text)}</w:t></w:r></w:p>'
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "word/document.xml":
                xml = data.decode("utf-8")
                xml = xml.replace("</w:body>", paragraph + "</w:body>")
                data = xml.encode("utf-8")
            zout.writestr(info, data)
    return out.getvalue()


def _docx_xml_text(docx_bytes: bytes) -> str:
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(docx_bytes), "r") as zf:
        return "\n".join(zf.read(name).decode("utf-8", errors="ignore") for name in zf.namelist() if name.endswith(".xml"))


def test_v4_session_restore_requires_changes_and_blocks_unchanged_baseline():
    """Default UI fallback must not silently create a jawny copy from the initial
    untouched _CSM_anon.docx when the user's edits are in another Word window.
    """
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "bez-zmian.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

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
    assert "bez zmian" in restore_response.text or "Ctrl+S" in restore_response.text


def test_v4_session_restore_with_saved_edited_anon_applies_changes_and_deanonymizes():
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "zapisany-edit.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_path = Path(prepared["anon_path"])
    edited = _append_docx_paragraph(anon_path.read_bytes(), "Nowa klauzula dla [OSOBA_1].")
    anon_path.write_bytes(edited)

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
    assert restored["input_changed_from_prepare"] is True
    restored_xml = _docx_xml_text(Path(restored["restored_path"]).read_bytes())
    assert "Nowa klauzula" in restored_xml
    assert "Jan Kowalski" in restored_xml
    assert "[OSOBA_1]" not in restored_xml


def test_v4_session_restore_uses_open_word_savecopyas_before_stale_disk_file(monkeypatch):
    """If Word has the edited _CSM_anon.docx open but the disk file is still the
    untouched baseline, the backend should use the COM SaveCopyAs live copy.
    """
    import api as api_module

    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "live-word-edit.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_path = Path(prepared["anon_path"])
    live_edited = _append_docx_paragraph(anon_path.read_bytes(), "Zmiana z otwartego Worda dla [OSOBA_1].")

    def fake_live_copy(path):
        assert Path(path).resolve() == anon_path.resolve()
        return live_edited, None

    monkeypatch.setattr(api_module, "_read_open_word_document_copy", fake_live_copy)
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
    assert restored["input_changed_from_prepare"] is True
    assert restored["negotiation_report"].get("restore_source") == "word-com-savecopyas"
    restored_xml = _docx_xml_text(Path(restored["restored_path"]).read_bytes())
    assert "Zmiana z otwartego Worda" in restored_xml
    assert "Jan Kowalski" in restored_xml
    assert "[OSOBA_1]" not in restored_xml


def _replace_docx_xml_text(docx: bytes, old: str, new: str) -> bytes:
    import io
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx), "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    xml = data.decode("utf-8")
                    assert old in xml, old
                    data = xml.replace(old, new).encode("utf-8")
                zout.writestr(info, data)
    return out.getvalue()


def _docx_visible_text(docx: bytes) -> str:
    import io
    import zipfile
    from lxml import etree

    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(docx), "r") as zf:
        root = etree.fromstring(zf.read("word/document.xml"))
    return "".join(root.xpath(".//w:t/text() | .//w:delText/text()", namespaces=ns))


def test_v4_session_restore_last_applies_saved_edits_and_deanonymizes_when_required():
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "zmiany.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_path = Path(prepared["anon_path"])
    edited = _replace_docx_xml_text(
        anon_path.read_bytes(),
        "podpisał dokument.",
        "podpisał dokument po negocjacjach.",
    )
    anon_path.write_bytes(edited)

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
    assert restored["input_changed_from_prepare"] is True
    text = _docx_visible_text(Path(restored["restored_path"]).read_bytes())
    assert "podpisał dokument po negocjacjach." in text
    assert "Jan Kowalski" in text
    assert "[OSOBA_" not in text


def test_v4_session_restore_last_refuses_unchanged_baseline_when_ui_requires_changes():
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "bez-zmian.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

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
