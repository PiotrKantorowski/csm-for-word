from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKPANE = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
API = (ROOT / "server" / "api.py").read_text(encoding="utf-8")


def test_loads_frontend_modules_before_taskpane():
    state_idx = HTML.index("state-machine.js?v=1.6-20260710")
    bridge_idx = HTML.index("word-bridge.js?v=1.6-20260710")
    taskpane_idx = HTML.index("taskpane.js?v=1.6-20260710")
    assert state_idx < taskpane_idx
    assert bridge_idx < taskpane_idx
    assert "v1.6" in HTML


def test_backend_and_panel_versions_are_current():
    assert 'from version import APP_VERSION' in API
    assert 'const APP_VERSION = "1.6"' in TASKPANE


def test_health_endpoint_returns_paths():
    assert "MAPS_DIR" in API
    assert "INSTALL_BACKUPS_DIR" in API
    assert '"paths"' in API or "'paths'" in API
    assert "str(MAPS_DIR)" in API
    assert "str(INSTALL_BACKUPS_DIR)" in API


def test_taskpane_is_bridge_only_no_word_run_fallbacks():
    # These legacy fallback patterns must NOT exist in the current panel.
    # word-bridge.js is now the sole Word API layer.
    forbidden = [
        "Office.context.document.getFileAsync",
        "context.document.body.insertText",
        "context.document.body.insertOoxml",
        "target.body.search",
        "bytesToBase64",
        "sliceDataToBytes",
        "hasUnsavedTrackedChanges",
        "wordTrackOffValue",
        "headerFooterTypes",
    ]
    for marker in forbidden:
        assert marker not in TASKPANE, (
            f"Legacy fallback marker still present in taskpane.js: {marker!r}. "
            "Iteration 5 requires all Word API calls to go through word-bridge.js."
        )


def test_taskpane_still_uses_word_bridge():
    # In the current panel all calls go through requireBridge() helper
    for bridge_marker in [
        "requireBridge().readTrackingMode",
        "requireBridge().readBodyText",
        "requireBridge().readBodyOoxml",
        "requireBridge().replaceBodyWithText",
        "requireBridge().replaceBodyWithOoxml",
        "requireBridge().collectOoxmlParts",
        "requireBridge().replaceOoxmlParts",
        "requireBridge().applySearchReplacePairs",
        "requireBridge().getCompressedDocumentBase64",
    ]:
        assert bridge_marker in TASKPANE, (
            f"Expected bridge call missing from taskpane.js: {bridge_marker!r}"
        )


def test_taskpane_uses_v3_state_machine():
    for marker in [
        "readSafeModeSnapshot",
        "sm.readStateSnapshot",
        "sm.ensureCleanState",
        "sm.markMasking",
        "sm.markMasked",
        "sm.markRestoring",
        "sm.markRestored",
        "sm.markError",
    ]:
        assert marker in TASKPANE, f"State machine call missing: {marker!r}"


def test_taskpane_no_legacy_mirror_writes():
    # v3 state machine is the sole state source — old claudeSafeMode.* mirror
    # writes must be gone (MODE, MAP, SESSION keys must not be saveSetting targets).
    assert 'saveSetting(MAP_SETTING_KEY' not in TASKPANE
    assert 'saveSetting(MODE_SETTING_KEY' not in TASKPANE
    assert 'saveSetting(SESSION_SETTING_KEY' not in TASKPANE


def test_taskpane_has_require_bridge_guard():
    assert "requireBridge" in TASKPANE
    assert "word-bridge.js nie jest załadowany" in TASKPANE


def test_taskpane_has_install_paths_support():
    assert "installPaths" in TASKPANE
    assert "backupFolderLabel" in TASKPANE
    assert "mapsDir" in TASKPANE


def test_taskpane_replacements_null_guard():
    # Bug 2 fix: (restoreData.replacements || []) must be used, not bare .replacements
    assert "(restoreData.replacements || [])" in TASKPANE


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK: taskpane integration static tests passed")
