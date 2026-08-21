"""Tracked-change preserve mode tests.

Critical acceptance: preserve masking must keep the number of <w:ins> and
<w:del> elements exactly identical before and after masking.
"""
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

from server.tc_engine import mask_docx_preserving_tc, restore_docx_preserving_tc, overlay_original_revision_contexts  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS


def _content_types() -> str:
    return """<?xml version='1.0' encoding='UTF-8'?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/comments.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>
</Types>"""


def _rels() -> str:
    return """<?xml version='1.0' encoding='UTF-8'?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""


def _document_xml() -> str:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<w:document xmlns:w="{W_NS}">
  <w:body>
    <w:p><w:r><w:t>Umowa numer Rep. B 9876/2025.</w:t></w:r></w:p>
    <w:p>
      <w:ins w:id="1" w:author="Anna Nowak" w:date="2025-01-02T10:00:00Z">
        <w:r><w:t>Jan Kowalski</w:t></w:r>
      </w:ins>
      <w:r><w:t> podpisał dokument.</w:t></w:r>
    </w:p>
    <w:p>
      <w:del w:id="2" w:author="Piotr Zieliński" w:date="2025-01-03T10:00:00Z">
        <w:r><w:delText>PESEL 44051401359</w:delText></w:r>
      </w:del>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""


def _comments_xml() -> str:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<w:comments xmlns:w="{W_NS}">
  <w:comment w:id="0" w:author="Maria Wiśniewska" w:date="2025-01-04T10:00:00Z">
    <w:p><w:r><w:t>decyzją nr SKO-OL/4101/16/2023</w:t></w:r></w:p>
  </w:comment>
</w:comments>"""


def _build_docx_with_revisions() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _rels())
        zf.writestr("word/document.xml", _document_xml())
        zf.writestr("word/comments.xml", _comments_xml())
    return buf.getvalue()


def _tree(docx: bytes, name: str = "word/document.xml"):
    with zipfile.ZipFile(io.BytesIO(docx)) as zf:
        return etree.fromstring(zf.read(name))


def _count(docx: bytes, local: str) -> int:
    return len(_tree(docx).findall(f".//{W}{local}"))


def _all_text(docx: bytes, name: str = "word/document.xml") -> str:
    tree = _tree(docx, name)
    return "".join(t.text or "" for t in tree.findall(f".//{W}t")) + "".join(t.text or "" for t in tree.findall(f".//{W}delText"))


def test_w_ins_text_is_masked_but_wrapper_preserved():
    docx = _build_docx_with_revisions()
    masked, replacements, report = mask_docx_preserving_tc(docx, mode="preserve")
    tree = _tree(masked)
    ins_elements = tree.findall(f".//{W}ins")
    assert len(ins_elements) == 1, "Insertion wrapper was removed or duplicated"
    assert ins_elements[0].get(f"{W}author") is not None, "Author attribute lost"
    assert ins_elements[0].get(f"{W}id") == "1", "ID attribute lost"
    full_text = "".join(t.text or "" for t in ins_elements[0].findall(f".//{W}t"))
    assert "Jan Kowalski" not in full_text, "Original name leaked inside <w:ins>"
    assert "[OSOBA_" in full_text, "Placeholder missing inside <w:ins>"
    assert report["revisions_summary"]["preserved"] is True
    assert replacements


def test_w_del_text_is_masked():
    docx = _build_docx_with_revisions()
    masked, _replacements, _report = mask_docx_preserving_tc(docx, mode="preserve")
    tree = _tree(masked)
    del_elements = tree.findall(f".//{W}del")
    assert len(del_elements) == 1, "Deletion wrapper was removed or duplicated"
    full_deleted = "".join(t.text or "" for t in del_elements[0].findall(f".//{W}delText"))
    assert "44051401359" not in full_deleted, "Original PESEL leaked inside <w:delText>"
    assert "[PESEL_" in full_deleted, "PESEL placeholder missing inside <w:delText>"


def test_revision_author_pii_is_masked_and_restorable():
    docx = _build_docx_with_revisions()
    masked, replacements, _report = mask_docx_preserving_tc(docx, mode="preserve")
    xml = etree.tostring(_tree(masked), encoding="unicode")
    assert "Anna Nowak" not in xml
    assert "Piotr Zieliński" not in xml
    assert "[OSOBA_" in xml
    restored, restore_report = restore_docx_preserving_tc(masked, replacements)
    restored_xml = etree.tostring(_tree(restored), encoding="unicode")
    assert "Anna Nowak" in restored_xml
    assert "Piotr Zieliński" in restored_xml
    assert restore_report["all_found"] is True


def test_no_new_revisions_are_created_critical_counts_identical():
    docx = _build_docx_with_revisions()
    ins_before = _count(docx, "ins")
    del_before = _count(docx, "del")
    masked, _replacements, _report = mask_docx_preserving_tc(docx, mode="preserve")
    ins_after = _count(masked, "ins")
    del_after = _count(masked, "del")
    assert ins_after == ins_before, f"New <w:ins> created: {ins_before} -> {ins_after}"
    assert del_after == del_before, f"New <w:del> created: {del_before} -> {del_after}"



def _flatten_revision_wrappers(docx: bytes) -> bytes:
    """Simulate a Word/Claude round-trip that loses revision wrappers."""
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx), "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    root = etree.fromstring(data)
                    for el in sorted(
                        [e for e in root.iter() if etree.QName(e).localname in {"ins", "del", "moveFrom", "moveTo"}],
                        key=lambda e: len(list(e.iterancestors())),
                        reverse=True,
                    ):
                        for node in el.iter():
                            if etree.QName(node).localname == "delText":
                                node.tag = W + "t"
                        parent = el.getparent()
                        if parent is None:
                            continue
                        idx = parent.index(el)
                        for child in list(el):
                            el.remove(child)
                            parent.insert(idx, child)
                            idx += 1
                        parent.remove(el)
                    data = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
                zout.writestr(info, data)
    return out.getvalue()


def test_restore_reapplies_original_revision_context_when_anon_copy_was_flattened():
    # Since CSM 1.0 rc28: Case-B re-wrapping is only applied to deletion contexts
    # (<w:del>/<w:moveFrom>), never to insertion contexts (<w:ins>/<w:moveTo>).
    # Rationale: re-creating <w:ins> wrappers caused every pseudonymised value to
    # appear as a tracked insertion when the original document was written with Track
    # Changes permanently enabled.  Deleted text must remain marked as deleted after
    # restore; inserted (accepted) text is left as plain text.
    original = _build_docx_with_revisions()
    masked, replacements, _report = mask_docx_preserving_tc(original, mode="preserve")
    flattened_masked = _flatten_revision_wrappers(masked)

    restored_without_overlay, pre_report = restore_docx_preserving_tc(flattened_masked, replacements)
    assert pre_report["restored_occurrences"] >= 2

    restored, overlay_report = overlay_original_revision_contexts(restored_without_overlay, original, replacements)
    # Both ins and del fragments are still *collected* (available), but only del is *reapplied* via Case B.
    assert overlay_report["available_fragments"] >= 2
    assert overlay_report["reapplied_fragments"] >= 1  # at least the del fragment

    tree = _tree(restored)
    del_text = "".join(t.text or "" for t in tree.findall(f".//{W}del//{W}delText"))
    # Deletion context is preserved: PESEL that was deleted stays in <w:del>.
    assert "44051401359" in del_text
    # Insertion context: Jan Kowalski was originally in <w:ins>, but after flatten+restore
    # it ends up as plain text (the insertion is considered accepted).
    all_text = "".join(t.text or "" for t in tree.iter(f"{W}t")) + "".join(t.text or "" for t in tree.iter(f"{W}delText"))
    assert "Jan Kowalski" in all_text
    assert "44051401359" not in "".join(t.text or "" for t in tree.findall(f".//{W}body/{W}p/{W}r/{W}t"))

def run_all():
    test_w_ins_text_is_masked_but_wrapper_preserved()
    test_w_del_text_is_masked()
    test_revision_author_pii_is_masked_and_restorable()
    test_no_new_revisions_are_created_critical_counts_identical()
    test_restore_reapplies_original_revision_context_when_anon_copy_was_flattened()
    print("OK: tracked-change preserve mode tests passed")


if __name__ == "__main__":
    run_all()


def _document_xml_revision_with_surrounding_text() -> str:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<w:document xmlns:w="{W_NS}">
  <w:body>
    <w:p>
      <w:ins w:id="7" w:author="Tester" w:date="2025-02-03T10:00:00Z">
        <w:r><w:t>Dodano stronę Jan Kowalski do umowy.</w:t></w:r>
      </w:ins>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""


def _build_docx_with_surrounding_revision_text() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _rels())
        zf.writestr("word/document.xml", _document_xml_revision_with_surrounding_text())
    return buf.getvalue()


def _replace_document_text(docx: bytes, old: str, new: str) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(docx), "r") as zin:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    data = data.replace(old.encode("utf-8"), new.encode("utf-8"))
                zout.writestr(info, data)
    return out.getvalue()


def test_restore_rebuilds_revision_around_value_when_surrounding_text_changed():
    # Insertion context is NOT rebuilt in Case B (see test above for rationale).
    # The value stays as plain text; surrounding text changes are preserved.
    original = _build_docx_with_surrounding_revision_text()
    masked, replacements, _report = mask_docx_preserving_tc(original, mode="preserve")
    flattened_masked = _flatten_revision_wrappers(masked)
    restored_without_overlay, _pre_report = restore_docx_preserving_tc(flattened_masked, replacements)
    # Simulate Claude/Word changing text around the restored protected value.
    edited = _replace_document_text(restored_without_overlay, "Dodano stronę Jan Kowalski do umowy.", "Po edycji Jan Kowalski pozostaje stroną.")

    restored, overlay_report = overlay_original_revision_contexts(edited, original, replacements)
    # No deletion fragments here → reapplied may be 0.
    tree = _tree(restored)
    normal_text = "".join(t.text or "" for t in tree.findall(f".//{W}body/{W}p/{W}r/{W}t"))
    # Jan Kowalski is in plain text (insertion context not re-created by Case B).
    assert "Jan Kowalski" in normal_text
    assert "Po edycji " in normal_text
    assert " pozostaje stroną." in normal_text


def _document_xml_duplicate_normal_and_tracked_name() -> str:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<w:document xmlns:w=\"{W_NS}\">
  <w:body>
    <w:p><w:r><w:t>Poza zmianami Jan Kowalski występuje jako pełnomocnik.</w:t></w:r></w:p>
    <w:p>
      <w:ins w:id=\"12\" w:author=\"Tester\" w:date=\"2025-02-03T10:00:00Z\">
        <w:r><w:t>Dodano stronę Jan Kowalski do umowy.</w:t></w:r>
      </w:ins>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""


def _build_docx_duplicate_normal_and_tracked_name() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _rels())
        zf.writestr("word/document.xml", _document_xml_duplicate_normal_and_tracked_name())
    return buf.getvalue()


def test_restore_rebuilds_revision_at_placeholder_position_not_first_clear_duplicate():
    # Since CSM 1.0 rc28: insertion TC (<w:ins>) is NOT rebuilt by the pre-restore
    # pass.  Only deletion contexts are reconstructed.  This prevents every
    # pseudonymised value from appearing as a tracked insertion in documents that
    # were typed with Track Changes permanently enabled.
    # Both occurrences of "Jan Kowalski" therefore return as plain text after restore.
    from server.tc_engine import restore_docx_preserving_tc_with_original_context

    original = _build_docx_duplicate_normal_and_tracked_name()
    masked, replacements, _report = mask_docx_preserving_tc(original, mode="preserve")
    flattened_masked = _flatten_revision_wrappers(masked)
    # Simulate Claude changing only the sentence around the tracked placeholder.
    edited = _replace_document_text(flattened_masked, "Dodano stronę [OSOBA_1] do umowy.", "Po edycji [OSOBA_1] pozostaje stroną.")

    restored, report = restore_docx_preserving_tc_with_original_context(edited, replacements, original)
    # No insertion TC rebuilt (changed from >= 1 to 0).
    assert report["pre_revision_context_rebuild"]["rebuilt_revision_placeholders"] == 0
    tree = _tree(restored)
    normal_text = "".join(t.text or "" for t in tree.findall(f".//{W}body/{W}p/{W}r/{W}t"))
    # Both occurrences are plain text.
    assert "Jan Kowalski" in normal_text
    assert "Po edycji " in normal_text
    assert " pozostaje stroną." in normal_text
    assert "Poza zmianami Jan Kowalski występuje jako pełnomocnik." in normal_text


def _document_xml_two_revision_authors(author1: str, author2: str) -> str:
    return f"""<?xml version='1.0' encoding='UTF-8'?>
<w:document xmlns:w=\"{W_NS}\">
  <w:body>
    <w:p>
      <w:ins w:id=\"21\" w:author=\"{author1}\" w:date=\"2025-02-03T10:00:00Z\">
        <w:r><w:t>Jan Kowalski</w:t></w:r>
      </w:ins>
    </w:p>
    <w:p>
      <w:ins w:id=\"22\" w:author=\"{author2}\" w:date=\"2025-02-04T10:00:00Z\">
        <w:r><w:t>Jan Kowalski</w:t></w:r>
      </w:ins>
    </w:p>
    <w:sectPr/>
  </w:body>
</w:document>"""


def _build_docx_two_revision_authors(author1: str, author2: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _rels())
        zf.writestr("word/document.xml", _document_xml_two_revision_authors(author1, author2))
    return buf.getvalue()


def test_overlay_fixes_wrong_revision_author_even_when_same_value_already_has_correct_author():
    original = _build_docx_two_revision_authors("Jan Kowalski", "Jan Kowalski")
    restored_with_mixed_authors = _build_docx_two_revision_authors("Jan Kowalski", "Osoba_1")
    replacements = [{"placeholder": "[OSOBA_1]", "original": "Jan Kowalski", "category": "PERSON"}]

    restored, overlay_report = overlay_original_revision_contexts(restored_with_mixed_authors, original, replacements)

    assert overlay_report["reapplied_fragments"] >= 1
    tree = _tree(restored)
    authors = [el.get(f"{W}author") for el in tree.findall(f".//{W}ins")]
    assert authors == ["Jan Kowalski", "Jan Kowalski"]
    assert "Osoba_1" not in etree.tostring(tree, encoding="unicode")
