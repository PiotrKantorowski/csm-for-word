from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")


def test_manual_restore_from_file_is_available_in_main_docx_flow() -> None:
    assert 'id="manualRestoreFile"' in HTML
    assert 'type="file"' in HTML
    assert 'accept=".docx' in HTML
    assert 'id="btnV4RestoreManual"' in HTML
    assert 'Awaryjnie przywróć wersję jawną z pliku' in HTML
    assert 'id="manualRestoreHint"' in HTML


def test_manual_restore_button_is_bound_and_uses_current_restore_endpoint() -> None:
    assert 'bindButton("btnV4RestoreManual", v4RestoreManualDocxCopy)' in JS
    assert 'async function v4RestoreManualDocxCopy()' in JS
    assert 'selectedManualRestoreFile' in JS
    assert 'fileToBase64' in JS
    assert 'new FileReader()' in JS
    assert 'apiPostHeavy("/v4/current/restore"' in JS or 'apiPost("/v4/current/restore"' in JS
    assert 'filename: file.name || "dokument_CSM_anon.docx"' in JS
    assert 'map_id: fallbackMapId' in JS


def test_prepare_attempts_to_auto_open_csm_taskpane_in_anon_doc() -> None:
    assert 'OFFICE_AUTO_SHOW_TASKPANE_KEY = "Office.AutoShowTaskpaneWithDocument"' in JS
    assert 'enableTaskpaneAutoShowForCurrentDocument("prepare-anon-copy")' in JS
    assert 'Panel CSM powinien automatycznie otworzyć się także w pliku roboczym' in JS
    # The flag must be saved before the package is read and sent to the backend.
    assert JS.index('enableTaskpaneAutoShowForCurrentDocument("prepare-anon-copy")') < JS.index('getCompressedDocumentBase64WithTimeout(30000)')


def test_v4_session_is_remembered_outside_active_office_document() -> None:
    assert 'safeLocalStorageSet(V4_LAST_MAP_SETTING_KEY' in JS
    assert 'safeLocalStorageSet(V4_LAST_SESSION_ID_KEY' in JS
    assert 'safeLocalStorageSet(V4_LAST_ANON_PATH_KEY' in JS
    assert 'function lastV4MapId()' in JS
    assert 'function lastV4SessionId()' in JS
    assert 'await rememberV4Session(data)' in JS


def test_v4_anon_document_status_is_detected_when_taskpane_opens_in_new_file() -> None:
    assert 'readV4CurrentStatusSafe' in JS
    assert 'apiPost("/v4/current/status"' in JS
    assert 'docContext.kind === "anon"' in JS
    assert 'inferFilenameKind' in JS
    assert 'Pracujesz na kopii dla Claude' in JS
