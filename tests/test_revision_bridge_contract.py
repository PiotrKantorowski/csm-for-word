from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
TASKPANE = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
REVISION_BRIDGE = (ROOT / "addin" / "revision_bridge.js").read_text(encoding="utf-8")
VALIDATE = (ROOT / "addin" / "scripts" / "validate-static.js").read_text(encoding="utf-8")


def test_revision_bridge_is_loaded_between_word_bridge_and_taskpane():
    word_idx = HTML.index("word-bridge.js?v=1.6-20260710")
    revision_idx = HTML.index("revision_bridge.js?v=1.6-20260710")
    taskpane_idx = HTML.index("taskpane.js?v=1.6-20260710")
    assert word_idx < revision_idx < taskpane_idx


def test_revision_bridge_exposes_anchor_and_custom_xml_contract():
    for marker in [
        "CSMRevisionBridge",
        "ANCHOR_PREFIX = \"CSM_ANCHOR:\"",
        "captureSelectionAnchor",
        "getReviewedText(WordApi.ChangeTrackingVersion.original)",
        "getReviewedText(WordApi.ChangeTrackingVersion.current)",
        "selection.insertContentControl()",
        "getContentControls().getByTag",
        "inspectRevisionAnchors",
        "upsertRevisionMap",
        "readRevisionMap",
        "deleteRevisionMap",
        "buildDocumentMetadata",
        "MAP_SETTING_KEYS",
        "CSM_RevisionMapPartId",
        "CSM_RevisionMapId",
        "CSM_RevisionEngineVersion",
        "CSM_RevisionRestoreStrategy",
        "sourcePart",
        "paragraphId",
        "<csm:strategy",
        "0.5.2-revision-plan",
        "0.5.2-revision-map",
        "customXmlParts.add",
        "customXmlParts.getByNamespace(MAP_NAMESPACE)",
        "context.document.settings",
        "context.document.properties.customProperties",
        "https://skills.kancelariakantorowski.pl/csm/revision-map/1",
    ]:
        assert marker in REVISION_BRIDGE


def test_taskpane_can_see_revision_bridge_without_word_logic_duplication():
    assert "function revisionBridge" in TASKPANE
    assert "function requireRevisionBridge" in TASKPANE
    assert "revision_bridge.js nie jest załadowany" in TASKPANE
    assert "inspectRevisionAnchors" in TASKPANE
    assert "persistRevisionMapForCurrentDocument" in TASKPANE
    assert "/v2/revision/anonymize" in TASKPANE
    assert "upsertRevisionMap" in TASKPANE
    assert "revisionMapPersistence" in TASKPANE
    start = TASKPANE.index("async function preRestoreRevisionAwareRangePass")
    end = TASKPANE.index("async function restoreFromLastSavedAnonPath", start)
    block = TASKPANE[start:end]
    assert "revisionAnchorAudit" in block
    assert "Word.run" not in block
    assert "insertContentControl" not in block


def test_static_validator_includes_revision_bridge():
    assert "addin/revision_bridge.js" in VALIDATE
