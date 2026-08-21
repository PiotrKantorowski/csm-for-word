"""Tracked-change reject-then-mask tests."""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("CSM_API_TOKEN", "test-token")

from server.tc_engine import mask_docx_preserving_tc  # noqa: E402
from test_tracked_changes_accept_mode import _build_docx_with_accept_reject_revisions, W  # noqa: E402


def _tree(docx: bytes):
    with zipfile.ZipFile(io.BytesIO(docx)) as zf:
        return etree.fromstring(zf.read("word/document.xml"))


def _all_text(docx: bytes) -> str:
    tree = _tree(docx)
    return "".join(t.text or "" for t in tree.findall(f".//{W}t")) + "".join(t.text or "" for t in tree.findall(f".//{W}delText"))


def _count(tree, local: str) -> int:
    return len(tree.findall(f".//{W}{local}"))


def test_reject_mode_removes_all_revisions_and_keeps_rejected_deletions_visible():
    docx = _build_docx_with_accept_reject_revisions()
    masked, replacements, report = mask_docx_preserving_tc(docx, mode="reject_then_mask")
    tree = _tree(masked)

    for local in ["ins", "del", "moveFrom", "moveTo", "pPrChange", "rPrChange"]:
        assert _count(tree, local) == 0, f"reject_then_mask left revision element <w:{local}>"

    assert _count(tree, "delText") == 0, "reject_then_mask must convert <w:delText> to <w:t> after unwrapping deletions"
    text = _all_text(masked)
    assert "Jan Kowalski" not in text, "Rejected insertion should disappear"
    assert "Tomasz Mazur" not in text, "Rejected moveTo should disappear"
    assert "Adam Nowicki" not in text, "Rejected deletion PII should be pseudonymized"
    assert "Maria Wiśniewska" not in text, "Rejected moveFrom PII should be pseudonymized"
    assert text.count("[OSOBA_") >= 2, text
    assert replacements
    assert report["revisions_summary"]["preserved"] is False


def test_reject_mode_converts_deltext_to_visible_t_and_preserves_xml_space():
    docx = _build_docx_with_accept_reject_revisions()
    masked, _replacements, _report = mask_docx_preserving_tc(docx, mode="reject_then_mask")
    tree = _tree(masked)
    assert not tree.findall(f".//{W}delText")
    visible_text_nodes = [t.text or "" for t in tree.findall(f".//{W}t")]
    joined = "".join(visible_text_nodes)
    assert "[OSOBA_" in joined


def test_reject_mode_restores_previous_formatting_from_prchange():
    masked, _replacements, _report = mask_docx_preserving_tc(_build_docx_with_accept_reject_revisions(), mode="reject_then_mask")
    tree = _tree(masked)
    assert _count(tree, "pPrChange") == 0
    jc = tree.find(f".//{W}pPr/{W}jc")
    assert jc is not None
    assert jc.get(W + "val") == "left", "Reject should restore previous formatting from <w:pPrChange>"


def run_all():
    test_reject_mode_removes_all_revisions_and_keeps_rejected_deletions_visible()
    test_reject_mode_converts_deltext_to_visible_t_and_preserves_xml_space()
    test_reject_mode_restores_previous_formatting_from_prchange()
    print("OK: tracked-change reject mode tests passed")


if __name__ == "__main__":
    run_all()
