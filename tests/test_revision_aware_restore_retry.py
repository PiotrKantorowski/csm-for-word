from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_restore_visible_retry_is_revision_aware():
    taskpane = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "preserveRevisionContext: true" in taskpane
    assert "applySearchReplacePairs(retryPairs" in taskpane
    assert "preserveRevisionContext: true" in taskpane


def test_word_bridge_inspects_range_ooxml_before_visible_retry():
    bridge = (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")
    assert "preserveRevisionContext" in bridge
    assert "range.getOoxml()" in bridge
    assert "ooxmlContainsRevisionMarkup" in bridge
    assert "trackAllValue" in bridge
    assert "wordTrackOffValue" in bridge


def test_word_bridge_no_longer_forces_all_revision_retry_off():
    bridge = (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")
    assert "Revision-aware retry for mask/restore" in bridge
    assert "replaceClassifiedRanges(classified.clean" in bridge
    assert "replaceClassifiedRanges(classified.tracked" in bridge
    assert "replaceClassifiedRanges(classified.clean, offValue)" in bridge
