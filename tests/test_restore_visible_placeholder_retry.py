from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKPANE = ROOT / "addin" / "taskpane.js"


def test_restores_visible_placeholders_when_word_does_not_apply_ooxml_replace():
    js = TASKPANE.read_text(encoding="utf-8")
    assert "usedVisibleRangeRetry" in js
    assert "Przywracanie strukturalne zostało wykonane, ale Word nadal pokazuje oznaczenia" in js
    assert 'buildRangePairs(replacementsPayload, "restore")' in js
    assert "applySearchReplacePairs(retryPairs" in js
    assert "postRestoreHasVisiblePlaceholder = await documentHasVisiblePlaceholder()" in js


def test_does_not_clear_map_before_visible_placeholder_check():
    js = TASKPANE.read_text(encoding="utf-8")
    visible_check = js.index("postRestoreHasVisiblePlaceholder = await documentHasVisiblePlaceholder()")
    clear_call = js.index("await clearSafeModeSettingsAfterRestore()")
    assert visible_check < clear_call
