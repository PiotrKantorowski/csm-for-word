"""Regression: applySearchReplacePairs must delegate to word-bridge.js.

In v0.2.38 runWithTrackChangesTemporarilyOff returned a wrapper object
({result, canControlTracking, previousMode}), while callers expected
applied.replaced. Earlier implementations lived in taskpane.js; current implementations
the entire implementation moved to word-bridge.js (bridge-only arch).
This test verifies that:
  - taskpane.js delegates applySearchReplacePairs to requireBridge()
  - word-bridge.js contains the actual runWithTrackChangesTemporarilyOff wrapper
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKPANE = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
BRIDGE = (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")

# taskpane.js must delegate to the bridge — no direct Word.run tracking logic
start = TASKPANE.index("async function applySearchReplacePairs")
end = TASKPANE.index("function buildRangeRestoreReport", start)
block = TASKPANE[start:end]

assert "requireBridge().applySearchReplacePairs" in block, \
    "taskpane.js applySearchReplacePairs must call requireBridge().applySearchReplacePairs"
assert "runWithTrackChangesTemporarilyOff" not in block, \
    "Word tracking logic must not be duplicated in taskpane.js — it lives in word-bridge.js"

# word-bridge.js must contain the actual tracking-aware wrapper
assert "runWithTrackChangesTemporarilyOff" in BRIDGE, \
    "word-bridge.js must contain runWithTrackChangesTemporarilyOff"
assert "applySearchReplacePairs" in BRIDGE, \
    "word-bridge.js must contain applySearchReplacePairs implementation"

print("OK: range wrapper regression test passed")
