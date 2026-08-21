"""Regression: restore must reassemble placeholders split across runs.

Reproduces a real production data-safety bug found on a heavily redlined
contract. When Word (or an AI round trip) splits a placeholder such as
``[FIRMA_3]`` across several <w:r> runs inside the same tracked-change wrapper
(``[FIRMA_3`` in one run, ``]`` in the next), the previous per-slot restore
never matched the placeholder in any single run. It left the truncated
``[FIRMA_3`` fragment visible in the "clear" document — and because the leftover
scan only matches bracket-closed placeholders, the corruption was reported as a
clean restore. The real document ended up with ~26 repeated ``[FIRMA_3``
fragments instead of the restored company name.

All values here are fictitious and only mirror the XML *structure* of the
production case.
"""
from __future__ import annotations

import io
import os
import re
import sys
import zipfile
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CSM_API_TOKEN", "test-token")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))

import tc_engine  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


def _make_docx(document_xml: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'>"
            "<Default Extension='xml' ContentType='application/xml'/>"
            "<Override PartName='/word/document.xml' ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml'/>"
            "</Types>",
        )
        z.writestr(
            "_rels/.rels",
            "<?xml version='1.0'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
            "<Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='word/document.xml'/>"
            "</Relationships>",
        )
        z.writestr("word/document.xml", document_xml)
    return buf.getvalue()


def _document_xml(docx_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        return z.read("word/document.xml").decode("utf-8")


def _split_placeholder_document(placeholder: str, repeats: int) -> str:
    # One <w:ins> wrapper containing the placeholder repeated `repeats` times,
    # each split as "<prefix>" | "]" across two separate runs, mirroring how
    # Word fragments a placeholder while tracking changes.
    prefix = placeholder[:-1]
    runs = []
    for _ in range(repeats):
        runs.append(f"<w:r><w:t>{prefix}</w:t></w:r>")
        runs.append("<w:r><w:t>]</w:t></w:r>")
        runs.append("<w:r><w:t xml:space='preserve'> </w:t></w:r>")
    return (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        "<w:body>"
        "<w:p><w:ins w:id='0' w:author='Autor Testowy' w:date='2026-07-02T08:17:00Z'>"
        + "".join(runs)
        + "</w:ins></w:p>"
        "</w:body></w:document>"
    )


def test_split_placeholder_inside_ins_is_reassembled_and_restored():
    placeholder = "[FIRMA_3]"
    original = "Kancelaria Fikcyjna Testowa"
    docx = _make_docx(_split_placeholder_document(placeholder, repeats=26))

    restored, report = tc_engine.restore_docx_preserving_tc(
        docx, [{"placeholder": placeholder, "original": original, "category": "COMPANY"}]
    )
    out = _document_xml(restored)

    # No truncated fragment (the exact production symptom).
    assert not re.search(r"\[FIRMA_3(?!\])", out), out
    assert "[FIRMA_3]" not in out
    # All 26 occurrences restored to the fictitious value.
    assert out.count(original) == 26
    assert report["restored_occurrences"] == 26
    assert report["missing_placeholders"] == []
    # Tracked-change wrapper is preserved (still inside <w:ins>).
    tree = etree.fromstring(out.encode("utf-8"))
    ins_text = "".join(t.text or "" for t in tree.xpath(".//w:ins//w:t", namespaces=NS))
    assert ins_text.count(original) == 26


def test_prefix_sibling_placeholders_are_not_shadowed():
    # "[FIRMA_3]" must not swallow the longer sibling "[FIRMA_3_ALIAS_1]".
    doc = (
        "<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
        "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'>"
        "<w:body>"
        "<w:p><w:r><w:t>A: [FIRMA_3] i B: [FIRMA_3_ALIAS_1].</w:t></w:r></w:p>"
        # Longer sibling also split across runs inside a revision.
        "<w:p><w:ins w:id='7' w:author='X' w:date='2026-01-01T00:00:00Z'>"
        "<w:r><w:t>[FIRMA_3_ALIAS_1</w:t></w:r><w:r><w:t>]</w:t></w:r>"
        "</w:ins></w:p>"
        "</w:body></w:document>"
    )
    docx = _make_docx(doc)
    reps = [
        {"placeholder": "[FIRMA_3]", "original": "Spolka Glowna", "category": "COMPANY"},
        {"placeholder": "[FIRMA_3_ALIAS_1]", "original": "SG", "category": "ALIAS"},
    ]
    restored, report = tc_engine.restore_docx_preserving_tc(docx, reps)
    out = _document_xml(restored)

    assert "[FIRMA_3" not in out, out
    assert "A: Spolka Glowna i B: SG." in out
    # The split sibling inside the revision was reassembled to its own value.
    tree = etree.fromstring(out.encode("utf-8"))
    ins_text = "".join(t.text or "" for t in tree.xpath(".//w:ins//w:t", namespaces=NS))
    assert ins_text == "SG"
    assert report["missing_placeholders"] == []
