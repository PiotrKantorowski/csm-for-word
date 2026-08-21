"""Regression: a failed Word pre-restore range pass must not abort restore.

Observed in v1.5: preRestoreRevisionAwareRangePass threw inside Office.js and
tryRestoreFromCurrentAnonPackage treated that as "cannot use the active Word
package". The flow then fell back to the saved *_CSM_anon.docx which was still
in its baseline state, so the user got HTTP 409 (stale_anon_input) instead of a
successful restore — even though the server could restore the active package
without the optional pre-pass.

The fix:
  * taskpane.js wraps the pre-pass in try/catch and continues with the
    package-based server restore, re-reading the package when the pass mutated
    (or could have mutated) the active document;
  * word-bridge.js makes the two-pass replacement resilient — OOXML inspection
    and per-phase syncs degrade gracefully instead of failing the whole call.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKPANE = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
BRIDGE = (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")


def test_taskpane_wraps_range_pass_and_continues_with_package_restore():
    call = TASKPANE.index("preRestoreRangePass = await preRestoreRevisionAwareRangePass")
    # The call must sit inside a try block whose catch keeps the flow alive.
    preceding = TASKPANE[max(0, call - 400):call]
    assert "try {" in preceding, "range pass call must be wrapped in try/catch"
    following = TASKPANE[call:call + 1600]
    assert "catch (rangePassError)" in following
    assert "failed: true" in following
    # After a failed pass the package must be re-read (half-applied replacements),
    # and a failed re-read must fall back to the pre-pass package, not abort.
    assert "preRestoreRangePass.used || preRestoreRangePass.failed" in TASKPANE
    refresh = TASKPANE.index("preRestoreRangePass.used || preRestoreRangePass.failed")
    refresh_block = TASKPANE[refresh:refresh + 900]
    assert "getCompressedDocumentBase64WithTimeout" in refresh_block
    assert "catch (refreshError)" in refresh_block


def test_taskpane_still_posts_current_restore_after_range_pass_block():
    pass_block = TASKPANE.index("preRestoreRangePass = await preRestoreRevisionAwareRangePass")
    post = TASKPANE.find('apiPostHeavy("/v4/current/restore"', pass_block)
    assert post > pass_block, "current-package restore POST must follow the range pass"


def test_bridge_two_pass_syncs_degrade_gracefully():
    assert "safeClientResultValue" in BRIDGE
    assert "safeClientResultValue(rangeOoxmlResults[i])" in BRIDGE
    assert "safeClientResultValue(paragraphOoxmlResults[i])" in BRIDGE
    # Direct .value reads of the OOXML client results must be gone.
    assert "rangeOoxmlResults[i] && rangeOoxmlResults[i].value" not in BRIDGE
    # Classification sync and per-phase replacement syncs are wrapped.
    classify = BRIDGE.index("const classifyRangesForPair")
    classify_block = BRIDGE[classify:BRIDGE.index("const replaceClassifiedRanges")]
    assert "try { await context.sync(); } catch (_) {}" in classify_block
    replace = BRIDGE.index("const replaceClassifiedRanges")
    replace_block = BRIDGE[replace:replace + 1200]
    assert "try { await context.sync(); } catch (_) { return 0; }" in replace_block
