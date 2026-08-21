from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_final6_current_restore_uses_word_range_preflight_before_package_restore():
    taskpane = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "preRestoreRevisionAwareRangePass" in taskpane
    assert "preserveRevisionContext: true" in taskpane
    assert "applySearchReplacePairs(pairs" in taskpane
    assert "range.getOoxml()" in (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")
    preflight = taskpane.index("preRestoreRangePass = await preRestoreRevisionAwareRangePass")
    second_package_read = taskpane.index("docxBase64 = await getCompressedDocumentBase64WithTimeout", preflight)
    server_restore = taskpane.find('apiPostHeavy("/v4/current/restore"', second_package_read)
    if server_restore < 0:
        server_restore = taskpane.index('apiPost("/v4/current/restore"', second_package_read)
    assert preflight < second_package_read < server_restore


def test_final6_preflight_reports_tracked_and_clean_counts():
    taskpane = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "replacedTracked" in taskpane
    assert "replacedClean" in taskpane
    assert "classifiedTracked" in taskpane
    assert "word-range-pre-restore" in taskpane
