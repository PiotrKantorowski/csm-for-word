"""Restore must not flatten tracked-change text."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
os.environ["CSM_API_TOKEN"] = "test-token"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))

from api import app  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS, "pkg": "http://schemas.microsoft.com/office/2006/xmlPackage"}


def _post(client: TestClient, url: str, payload: dict):
    return client.post(url, headers=HDR, json=payload)


def _body_with_ins_and_deltext() -> str:
    return (
        "<pkg:package xmlns:pkg='http://schemas.microsoft.com/office/2006/xmlPackage'>"
        "<pkg:part pkg:name='/word/document.xml'><pkg:xmlData>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        "<w:body><w:p>"
        "<w:r><w:t>Poza zmianami występuje Anna Zielińska.</w:t></w:r>"
        "<w:ins w:id='10' w:author='Tester'><w:r><w:t>Dodano Jan Kowalski PESEL 44051401359.</w:t></w:r></w:ins>"
        "<w:del w:id='11' w:author='Tester'><w:r><w:delText>Usunięto Maria Nowak NIP 8131689438.</w:delText></w:r></w:del>"
        "</w:p></w:body></w:document>"
        "</pkg:xmlData></pkg:part></pkg:package>"
    )


def _texts_under(tree: etree._Element, xpath: str) -> str:
    nodes = tree.xpath(xpath, namespaces=NS)
    return "".join(node.text or "" for node in nodes)


def test_restore_ooxml_parts_keeps_original_contexts_inside_ins_and_deltext():
    client = TestClient(app)
    source = _body_with_ins_and_deltext()
    mask = _post(client, "/mask_ooxml_parts", {"parts": {"body": source}, "original_text": ""})
    assert mask.status_code == 200, mask.text
    masked_body = mask.json()["parts"]["body"]
    assert "Jan Kowalski" not in masked_body
    assert "Maria Nowak" not in masked_body
    assert "<w:ins" in masked_body or ":ins" in masked_body
    assert "<w:del" in masked_body or ":del" in masked_body
    assert "delText" in masked_body

    restore = _post(client, "/restore_ooxml_parts", {"map_id": mask.json()["map_id"], "parts": mask.json()["parts"]})
    assert restore.status_code == 200, restore.text
    restored_body = restore.json()["parts"]["body"]
    report = restore.json()["restore_report"]
    assert report["missing_total"] == 0, report
    assert report["leftover_total_after_restore"] == 0, report

    tree = etree.fromstring(restored_body.encode("utf-8"))
    ins_text = _texts_under(tree, ".//w:ins//w:t")
    del_text = _texts_under(tree, ".//w:del//w:delText")
    normal_text = _texts_under(tree, ".//w:body/w:p/w:r/w:t")

    assert "Jan Kowalski" in ins_text
    assert "44051401359" in ins_text
    assert "Maria Nowak" in del_text
    assert "8131689438" in del_text
    assert "Anna Zielińska" in normal_text
    assert "Jan Kowalski" not in normal_text
    assert "Maria Nowak" not in normal_text


def test_taskpane_restore_forces_structural_ooxml_after_range_mode_and_preserves_tracking():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert 'const forceStructuralRestore = modeKind === "range" || modeKind === "parts" || modeKind === "package";' in js
    assert 'Przywracam wersję jawną w strukturze dokumentu Word' in js
    assert 'apiPost("/restore_ooxml_parts"' in js
    assert 'Nie używam trybu awaryjnego, aby nie odłączyć tekstu od historii zmian' in js
    assert 'preserveTrackChanges: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "range")' in js


def test_word_bridge_can_replace_ooxml_without_forcing_tracking_off():
    bridge = (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")
    assert "runPreservingTrackingMode" in bridge
    assert "options && options.preserveTrackChanges ? runPreservingTrackingMode : runWithTrackChangesTemporarilyOff" in bridge


def test_taskpane_mask_ooxml_parts_preserves_tracking_when_document_has_revisions():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert 'const requireTrackControl = Boolean(partsHadRevisionMarkup || trackingActuallyOn)' in js
    assert 'await replaceOoxmlParts(data.parts, {\n        requireTrackControl,\n        preserveTrackChanges: Boolean(partsHadRevisionMarkup || trackingActuallyOn)\n      });' in js


def test_taskpane_structural_restore_uses_real_preserve_track_changes_option():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert 'preserveRevisionMarkup' not in js
    assert 'preserveTrackChanges: Boolean(restorePartsHadRevisionMarkup || restoreTrackingOn || modeKind === "package" || modeKind === "range")' in js
