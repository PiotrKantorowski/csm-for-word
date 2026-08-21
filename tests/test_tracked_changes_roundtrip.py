"""Tracked-change roundtrip tests."""
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

from server.tc_engine import mask_docx_preserving_tc, restore_docx_preserving_tc  # noqa: E402
from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # noqa: E402


def _canonical_xml_parts(docx_bytes: bytes) -> dict[str, bytes]:
    parts: dict[str, bytes] = {}
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as zf:
        for name in sorted(zf.namelist()):
            if not name.lower().endswith(".xml"):
                continue
            root = etree.fromstring(zf.read(name))
            parts[name] = etree.tostring(root, method="c14n")
    return parts


def test_mask_then_restore_returns_canonical_content():
    original = _build_docx_with_revisions()
    masked, replacements, mask_report = mask_docx_preserving_tc(original, mode="preserve")
    restored, restore_report = restore_docx_preserving_tc(masked, replacements)
    assert restore_report["all_found"] is True
    assert restore_report["missing_total"] == 0
    assert _canonical_xml_parts(original) == _canonical_xml_parts(restored)
    assert mask_report["revisions_summary"]["ins_count"] == 1
    assert mask_report["revisions_summary"]["del_count"] == 1


def run_all():
    test_mask_then_restore_returns_canonical_content()
    print("OK: tracked-change roundtrip tests passed")


if __name__ == "__main__":
    run_all()
