from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_MACHINE = (ROOT / "addin" / "state-machine.js").read_text(encoding="utf-8")
WORD_BRIDGE = (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")
TASKPANE = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")


def test_frontend_modules_exist():
    assert (ROOT / "addin" / "state-machine.js").is_file()
    assert (ROOT / "addin" / "word-bridge.js").is_file()


def test_state_machine_uses_v3_document_settings_keys_only():
    for key in [
        "CSM_STATE_V3",
        "CSM_MAP_ID_V3",
        "CSM_SESSION_ID_V3",
        "CSM_LAST_TRANSITION_V3",
        "CSM_BACKUP_PATH_V3",
    ]:
        assert key in STATE_MACHINE
        assert f'settings.set({key}' in STATE_MACHINE or f'settings.set(CSM_{key.split("CSM_")[-1]}' in STATE_MACHINE

    legacy_markers = [
        "MODE_SETTING_KEY",
        "MAP_SETTING_KEY",
        "SESSION_SETTING_KEY",
        "claudeSafeMode.enabled",
        "claudeSafeMode.mapId",
        "claudeSafeMode.sessionId",
    ]
    for marker in legacy_markers:
        assert marker not in STATE_MACHINE, f"state-machine.js must not migrate or read legacy v0.2 setting {marker}"


def test_state_machine_declares_clean_default_and_safe_transitions():
    assert 'CLEAN: "CLEAN"' in STATE_MACHINE
    assert 'MASKING: "MASKING"' in STATE_MACHINE
    assert 'MASKED: "MASKED"' in STATE_MACHINE
    assert 'RESTORING: "RESTORING"' in STATE_MACHINE
    assert 'RESTORED: "RESTORED"' in STATE_MACHINE
    assert 'ERROR: "ERROR"' in STATE_MACHINE
    assert "function normalizeState" in STATE_MACHINE
    assert 'CSM_STATES.CLEAN' in STATE_MACHINE
    assert "CSM_ALLOWED_TRANSITIONS" in STATE_MACHINE
    assert "function transitionAllowed" in STATE_MACHINE
    assert "async function transitionTo" in STATE_MACHINE
    assert "Invalid CSM v3 state transition" in STATE_MACHINE


def test_state_machine_public_contract():
    for symbol in [
        "readStateSnapshot",
        "transitionAllowed",
        "transitionTo",
        "ensureCleanState",
        "markClean",
        "markMasking",
        "markMasked",
        "markRestoring",
        "markRestored",
        "markError",
        "CSMStateMachine",
    ]:
        assert symbol in STATE_MACHINE
    assert "root.CSMStateMachine = CSMStateMachine" in STATE_MACHINE
    assert "module.exports = CSMStateMachine" in STATE_MACHINE


def test_word_bridge_public_contract_and_word_api_usage():
    for symbol in [
        "CSMWordBridge",
        "runWithTrackChangesTemporarilyOff",
        "readTrackingMode",
        "readBodyText",
        "readBodyOoxml",
        "replaceBodyWithText",
        "replaceBodyWithOoxml",
        "collectOoxmlParts",
        "replaceOoxmlParts",
        "applySearchReplacePairs",
        "getCompressedDocumentBase64",
        "headerFooterTypes",
    ]:
        assert symbol in WORD_BRIDGE
    for marker in [
        "Word.run",
        "changeTrackingMode",
        "getOoxml()",
        "insertOoxml",
        "insertText",
        "body.search",
        "Office.FileType.Compressed",
        "getFileAsync",
        "getSliceAsync",
    ]:
        assert marker in WORD_BRIDGE
    assert "root.CSMWordBridge = CSMWordBridge" in WORD_BRIDGE
    assert "module.exports = CSMWordBridge" in WORD_BRIDGE


def test_taskpane_integration_uses_bridge_only():
    # All Word API calls go through requireBridge() — no bridge.x pattern
    assert "window.CSMStateMachine" in TASKPANE
    assert "window.CSMWordBridge" in TASKPANE
    assert "ensureDocumentStateReady" in TASKPANE
    assert "markDocumentMasking" in TASKPANE
    assert "markDocumentMasked" in TASKPANE
    assert "beginDocumentRestore" in TASKPANE
    assert "completeDocumentRestore" in TASKPANE
    assert "isSafeModeActive()" in TASKPANE

    # wrapper functions still exist in taskpane.js but delegate to requireBridge()
    for func in [
        "async function collectOoxmlParts",
        "async function replaceOoxmlParts",
        "async function applySearchReplacePairs",
        "async function maskVisibleTextByRange",
        "async function getCompressedDocumentBase64",
    ]:
        assert func in TASKPANE

    # calls now use requireBridge() helper, not bare bridge.x
    for bridge_call in [
        "requireBridge().collectOoxmlParts",
        "requireBridge().replaceOoxmlParts",
        "requireBridge().applySearchReplacePairs",
        "requireBridge().getCompressedDocumentBase64",
    ]:
        assert bridge_call in TASKPANE


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK: frontend state machine and Word bridge static tests passed")
