from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")


def _restore_function() -> str:
    return JS[JS.index("async function v4RestoreDocxCopy"):JS.index("async function v4RestoreManualDocxCopy")]


def test_restore_button_uses_verified_active_docx_then_saved_session_fallback() -> None:
    restore = _restore_function()
    assert 'apiPostHeavy("/v4/session/restore-last"' in JS or 'apiPost("/v4/session/restore-last"' in JS
    assert "restoreFromLastSavedAnonPath" in restore
    assert "tryRestoreFromCurrentAnonPackage(ctx" in restore
    assert 'apiPostHeavy("/v4/current/status"' in JS or 'apiPost("/v4/current/status"' in JS
    assert 'apiPostHeavy("/v4/current/restore"' in JS or 'apiPost("/v4/current/restore"' in JS
    assert "falls back to the saved" in restore


def test_restore_copy_tells_user_to_save_working_docx_before_session_restore() -> None:
    restore = _restore_function()
    assert "Ctrl+S" in restore
    assert "zapisanej kopii _CSM_anon.docx z sesji CSM" in restore
