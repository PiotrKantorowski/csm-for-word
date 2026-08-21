"""Iteration 7 — ambiguity warnings + PII-free audit summary."""
import base64
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

from api import app  # noqa: E402
from redactor import collect_ambiguous_person_warnings, make_replacements  # noqa: E402

client = TestClient(app)
HDR = {"X-CSM-Token": "test-token"}


# ─── collect_ambiguous_person_warnings (pure unit) ───────────────────────────

def test_warnings_empty_when_no_ambiguity():
    text = "Jan Kowalski podpisał umowę. Anna Nowak była świadkiem."
    _, reps = make_replacements(text)
    assert collect_ambiguous_person_warnings(reps) == []


def test_warning_for_shared_surname():
    text = "Jan Kowalski podpisał. Piotr Kowalski się zgodził."
    _, reps = make_replacements(text)
    warnings = collect_ambiguous_person_warnings(reps)
    assert len(warnings) == 1
    assert "niejednoznaczne nazwiska" in warnings[0]
    # Must NOT leak the actual surname
    assert "Kowalski" not in warnings[0]


def test_warning_for_shared_first_name():
    text = "Jan Kowalski podpisał. Jan Nowak też potwierdził."
    _, reps = make_replacements(text)
    warnings = collect_ambiguous_person_warnings(reps)
    assert any("niejednoznaczne imiona" in w for w in warnings)
    # Must NOT leak the actual first name
    for w in warnings:
        assert "Jan" not in w


def test_warning_for_both_simultaneously():
    text = "Jan Kowalski, Piotr Kowalski, Jan Nowak. Trzy osoby."
    _, reps = make_replacements(text)
    warnings = collect_ambiguous_person_warnings(reps)
    assert any("niejednoznaczne nazwiska" in w for w in warnings)
    assert any("niejednoznaczne imiona" in w for w in warnings)


# ─── /mask wires warnings through ────────────────────────────────────────────

def test_mask_endpoint_includes_ambiguity_warnings():
    r = client.post(
        "/mask",
        headers=HDR,
        json={"text": "Jan Kowalski podpisał. Piotr Kowalski się zgodził."},
    )
    assert r.status_code == 200, r.text
    warnings = r.json()["warnings"]
    assert any("niejednoznaczne nazwiska" in w for w in warnings)


def test_scan_endpoint_includes_ambiguity_warnings():
    r = client.post(
        "/scan",
        headers=HDR,
        json={"text": "Jan Kowalski podpisał. Jan Nowak również."},
    )
    assert r.status_code == 200, r.text
    warnings = r.json()["warnings"]
    assert any("niejednoznaczne imiona" in w for w in warnings)


# ─── /audit_summary endpoint ─────────────────────────────────────────────────

def test_audit_summary_returns_recent_entries():
    # Trigger one mask so the audit log has something to return
    client.post("/mask", headers=HDR, json={"text": "Anna Nowak podpisała."})
    r = client.get("/audit_summary?limit=10", headers=HDR)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"] == "1.6"
    assert isinstance(body["entries"], list)
    assert body["entries"], "audit_summary must return at least one entry after a mask call"


def test_audit_summary_strips_unexpected_fields():
    """If a future caller adds a non-allow-listed field to audit_log, it must
    not leak via /audit_summary."""
    from security import AUDIT_LOG_PATH
    AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    poisoned_marker = "PII_LEAK_TEST_MARKER_AINON"
    poisoned = {
        "timestamp": "2099-01-01T00:00:00Z",
        "event": "mask",
        "status": "ok",
        "category_counts": {"PERSON": 1},
        # This must NOT appear in /audit_summary output. We use a synthetic
        # marker (not a realistic name) so a residual line in audit.log does
        # not look like leaked PII to other tests (e.g. selftest.py's
        # `assert "Jan Kowalski" not in log_text`).
        "leaked_field": poisoned_marker,
        "secret_internal": "never-leak-me",
    }
    import json
    original = AUDIT_LOG_PATH.read_text(encoding="utf-8") if AUDIT_LOG_PATH.exists() else ""
    try:
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(poisoned) + "\n")

        r = client.get("/audit_summary?limit=500", headers=HDR)
        assert r.status_code == 200
        body = r.text
        assert "leaked_field" not in body
        assert "secret_internal" not in body
        assert poisoned_marker not in body
    finally:
        # Restore audit.log to its pre-test state so other tests do not see
        # the synthetic poisoned line. This keeps the log clean across runs.
        AUDIT_LOG_PATH.write_text(original, encoding="utf-8")


def test_audit_log_writes_engine_and_warnings_count():
    """The audit log records engine_version and warnings_count for v3 masks."""
    from tc_engine import ENGINE_VERSION as TC_ENGINE_VERSION
    # Build a minimal valid docx via existing helper from tc preserve mode test
    sys.path.insert(0, str(ROOT / "tests"))
    from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # type: ignore
    docx_b64 = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    r = client.post(
        "/mask_docx_v3",
        headers=HDR,
        json={"docx_base64": docx_b64, "mode": "preserve"},
    )
    assert r.status_code == 200, r.text

    summary = client.get("/audit_summary?limit=20", headers=HDR).json()["entries"]
    docx_v3_masks = [e for e in summary if e.get("mode") == "docx_v3" and e.get("event") == "mask"]
    assert docx_v3_masks, "docx_v3 mask entry must appear in audit summary"
    latest = docx_v3_masks[-1]
    assert latest.get("engine_version") == TC_ENGINE_VERSION
    assert "warnings_count" in latest


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK: ambiguity + audit tests passed")
