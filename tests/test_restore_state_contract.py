from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")


def test_restore_does_not_clear_mode_before_postcheck():
    clear_idx = JS.index("await clearSafeModeSettingsAfterRestore();")
    visible_idx = JS.index("let postRestoreHasVisiblePlaceholder = await documentHasVisiblePlaceholder();")
    unresolved_idx = JS.index("const unresolvedReport = restoreHasUnresolvedPlaceholders(restoreReport);")
    keep_idx = JS.index("await keepSafeModeActiveAfterFailedRestore(")
    assert visible_idx < clear_idx, "post-restore placeholder check must happen before clearing safe-mode settings"
    assert unresolved_idx < clear_idx, "restore report unresolved check must happen before clearing safe-mode settings"
    assert keep_idx < clear_idx, "failed restore must keep safe mode active before any settings cleanup path"


def test_failed_restore_keeps_map_and_mode_active():
    # State machine (markDocumentMasked) is the source of truth
    assert "async function keepSafeModeActiveAfterFailedRestore" in JS
    helper = JS.split("async function keepSafeModeActiveAfterFailedRestore", 1)[1].split("// ─── Document", 1)[0]
    assert 'markDocumentMasked' in helper
    assert 'restore-failed-keep-masked' in helper
    assert "Tryb Claude pozostaje aktywny" in helper


def test_restore_failure_does_not_auto_emergency_restore():
    restore_func = JS.split("async function disableSafeMode", 1)[1].split("async function emergencyRestoreOriginal", 1)[0]
    assert "await emergencyRestoreOriginal" not in restore_func
    assert "Nie uruchamiam automatycznie przywracania awaryjnego" in restore_func


def test_orphan_placeholders_use_restore_not_emergency_overwrite():
    main_action = JS.split("async function mainAction", 1)[1].split("async function enableSafeMode", 1)[0]
    assert "await disableSafeMode({ reason: \"odzyskiwanie po utracie stanu dokumentu\" })" in main_action
    assert "await emergencyRestoreOriginal" not in main_action
    refresh = JS.split("async function refreshDocumentState", 1)[1].split("function showTechnicalStatus", 1)[0]
    assert "Przywróć wersję jawną" in refresh
    assert "Przywróć z kopii awaryjnej" not in refresh


def test_tracked_change_failure_message_no_false_fallback_claim():
    assert "Przechodzę do stabilnego trybu awaryjnego" not in JS
    assert "Word nie zastosował bezpiecznie podmiany" in JS


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK: restore-state regression tests passed")
