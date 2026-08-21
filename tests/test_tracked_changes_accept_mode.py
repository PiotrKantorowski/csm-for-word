"""Tracked-change accept-then-mask tests."""
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

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = "{%s}" % W_NS


def _content_types() -> str:
    return """<?xml version='1.0' encoding='UTF-8'?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
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
    <w:p>
      <w:pPr>
        <w:jc w:val="center"/>
        <w:pPrChange w:id="10" w:author="Anna Nowak" w:date="2025-01-01T10:00:00Z">
          <w:pPr><w:jc w:val="left"/></w:pPr>
        </w:pPrChange>
      </w:pPr>
      <w:ins w:id="1" w:author="Anna Nowak" w:date="2025-01-02T10:00:00Z">
        <w:r><w:t>Jan Kowalski</w:t></w:r>
      </w:ins>
      <w:del w:id="2" w:author="Piotr Zieliński" w:date="2025-01-03T10:00:00Z">
        <w:r><w:delText>Adam Nowicki</w:delText></w:r>
      </w:del>
    </w:p>
    <w:p>
      <w:moveFrom w:id="3" w:author="Ewa Malinowska" w:date="2025-01-04T10:00:00Z">
        <w:r><w:t>Maria Wiśniewska</w:t></w:r>
      </w:moveFrom>
      <w:moveTo w:id="4" w:author="Ewa Malinowska" w:date="2025-01-04T10:05:00Z">
        <w:r><w:t>Tomasz Mazur</w:t></w:r>
      </w:moveTo>
    </w:p>
  </w:body>
</w:document>"""


def _build_docx_with_accept_reject_revisions() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _rels())
        zf.writestr("word/document.xml", _document_xml())
    return buf.getvalue()


def _tree(docx: bytes):
    with zipfile.ZipFile(io.BytesIO(docx)) as zf:
        return etree.fromstring(zf.read("word/document.xml"))


def _all_text(docx: bytes) -> str:
    tree = _tree(docx)
    return "".join(t.text or "" for t in tree.findall(f".//{W}t")) + "".join(t.text or "" for t in tree.findall(f".//{W}delText"))


def _count(tree, local: str) -> int:
    return len(tree.findall(f".//{W}{local}"))


def test_accept_mode_removes_all_revisions_and_keeps_accepted_text():
    docx = _build_docx_with_accept_reject_revisions()
    masked, replacements, report = mask_docx_preserving_tc(docx, mode="accept_then_mask")
    tree = _tree(masked)

    for local in ["ins", "del", "moveFrom", "moveTo", "pPrChange", "rPrChange"]:
        assert _count(tree, local) == 0, f"accept_then_mask left revision element <w:{local}>"

    text = _all_text(masked)
    assert "Adam Nowicki" not in text, "Accepted deletion should disappear"
    assert "Maria Wiśniewska" not in text, "Accepted moveFrom should disappear"
    assert "Jan Kowalski" not in text, "Inserted PII should be pseudonymized"
    assert "Tomasz Mazur" not in text, "Moved-to PII should be pseudonymized"
    assert text.count("[OSOBA_") >= 2, text
    assert replacements
    assert report["revisions_summary"]["preserved"] is False


def test_accept_mode_removes_formatting_revision_history_but_keeps_current_formatting():
    masked, _replacements, _report = mask_docx_preserving_tc(_build_docx_with_accept_reject_revisions(), mode="accept_then_mask")
    tree = _tree(masked)
    assert _count(tree, "pPrChange") == 0
    jc = tree.find(f".//{W}pPr/{W}jc")
    assert jc is not None
    assert jc.get(W + "val") == "center", "Accept should keep current formatting"


def run_all():
    test_accept_mode_removes_all_revisions_and_keeps_accepted_text()
    test_accept_mode_removes_formatting_revision_history_but_keeps_current_formatting()
    print("OK: tracked-change accept mode tests passed")


if __name__ == "__main__":
    run_all()
