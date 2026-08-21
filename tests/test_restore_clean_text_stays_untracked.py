"""Regression: restore must not turn never-tracked text into tracked changes.

Bug (v1.5): the two-pass replacement in word-bridge.js classified a search hit
as "tracked" whenever the surrounding PARAGRAPH contained any revision markup
(including formatting-only changes such as rPrChange). A placeholder that was
anonymized from plain, never-tracked text — but sat in a paragraph with some
other tracked change — was then replaced with Track Changes ON during the
pre-restore range pass, so the restored value showed up as a brand new tracked
change instead of ordinary unchanged text.

The fix classifies a hit as tracked only when the searched text itself sits
inside a content revision wrapper (w:ins / w:del / w:moveFrom / w:moveTo).
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "addin" / "word-bridge.js"


def test_bridge_classifies_by_text_inside_revision_not_whole_paragraph():
    bridge = BRIDGE.read_text(encoding="utf-8")
    assert "ooxmlRevisionMarkupCoversText" in bridge
    assert "ooxmlRevisionMarkupCoversText(rangeXml, pair.from)" in bridge
    assert "ooxmlRevisionMarkupCoversText(paragraphXml, pair.from)" in bridge
    # The old blanket classification must be gone from classifyRangesForPair.
    assert "ooxmlContainsRevisionMarkup(rangeXml) || ooxmlContainsRevisionMarkup(paragraphXml)" not in bridge


def _node_eval(expression: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not available")
    script = (
        "const bridge = require(%s);"
        "console.log(JSON.stringify(%s));"
    ) % (json.dumps(str(BRIDGE)), expression)
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip())


def test_plain_placeholder_in_paragraph_with_other_tracked_change_is_clean():
    # The bug scenario: paragraph has a tracked insertion of OTHER text, while
    # the placeholder itself lives in an ordinary run.
    paragraph = (
        '<w:p><w:ins w:id="1" w:author="X"><w:r><w:t>dopisane zdanie</w:t></w:r></w:ins>'
        '<w:r><w:t>Umowa z [PERSON_1] z dnia</w:t></w:r></w:p>'
    )
    covered = _node_eval(
        "bridge.ooxmlRevisionMarkupCoversText(%s, %s)" % (json.dumps(paragraph), json.dumps("[PERSON_1]"))
    )
    assert covered is False


def test_formatting_only_revision_does_not_mark_placeholder_tracked():
    paragraph = (
        '<w:p><w:pPr><w:rPr><w:rPrChange w:id="2" w:author="X"><w:b/></w:rPrChange></w:rPr></w:pPr>'
        '<w:r><w:t>[COMPANY_1]</w:t></w:r></w:p>'
    )
    covered = _node_eval(
        "bridge.ooxmlRevisionMarkupCoversText(%s, %s)" % (json.dumps(paragraph), json.dumps("[COMPANY_1]"))
    )
    assert covered is False


def test_placeholder_inside_tracked_insertion_is_still_tracked():
    paragraph = (
        '<w:p><w:ins w:id="3" w:author="X"><w:r><w:t>Pan [PERSON_2] oświadcza</w:t></w:r></w:ins></w:p>'
    )
    covered = _node_eval(
        "bridge.ooxmlRevisionMarkupCoversText(%s, %s)" % (json.dumps(paragraph), json.dumps("[PERSON_2]"))
    )
    assert covered is True


def test_placeholder_split_across_runs_inside_one_revision_is_tracked():
    paragraph = (
        '<w:p><w:ins w:id="4" w:author="X">'
        '<w:r><w:t>[PERSON</w:t></w:r><w:r><w:t>_3]</w:t></w:r>'
        '</w:ins></w:p>'
    )
    covered = _node_eval(
        "bridge.ooxmlRevisionMarkupCoversText(%s, %s)" % (json.dumps(paragraph), json.dumps("[PERSON_3]"))
    )
    assert covered is True


def test_placeholder_inside_tracked_deletion_is_tracked():
    paragraph = (
        '<w:p><w:del w:id="5" w:author="X"><w:r><w:delText>[ADDRESS_1]</w:delText></w:r></w:del></w:p>'
    )
    covered = _node_eval(
        "bridge.ooxmlRevisionMarkupCoversText(%s, %s)" % (json.dumps(paragraph), json.dumps("[ADDRESS_1]"))
    )
    assert covered is True


def test_original_value_with_xml_entities_is_matched_in_mask_direction():
    # Mask direction searches for the original value; XML stores "&" as "&amp;".
    paragraph = (
        '<w:p><w:ins w:id="6" w:author="X"><w:r><w:t>Kowalski &amp; Wspólnicy</w:t></w:r></w:ins></w:p>'
    )
    covered = _node_eval(
        "bridge.ooxmlRevisionMarkupCoversText(%s, %s)"
        % (json.dumps(paragraph), json.dumps("Kowalski & Wspólnicy"))
    )
    assert covered is True
