"""Manual-rules hardening (post-v1.5): word boundaries, hard-category
protection with force, inflection variants with ledger clustering, per-rule
accountability report, persisted rule levels and the controls dry-run preview.
"""
import base64
import os
import sys
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["CSM_API_TOKEN"] = "test-token"

from api import app  # noqa: E402
import rules_store  # noqa: E402
from redactor import (  # noqa: E402
    collect_findings_with_controls_report,
    make_replacements_with_controls,
)
from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # noqa: E402

pytestmark = pytest.mark.current

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)

VALID_PESEL = "44051401359"


def test_always_rule_respects_word_boundaries():
    text = "Umowa z firmą Alarmex. Strona otrzymała dokument."
    masked, _ = make_replacements_with_controls(text, {"always": [{"value": "Ala", "category": "MANUAL"}]})
    assert "otrzymała" in masked  # no mid-word masking
    assert "otrzym[MANUAL" not in masked


def test_never_substring_cannot_unmask_checksum_valid_pesel():
    text = f"PESEL {VALID_PESEL} należy do strony."
    findings, report = collect_findings_with_controls_report(text, {"never": ["4405"]})
    assert any(f.category == "PESEL" for f in findings)
    assert any("krótki numer" in w for w in report["warnings"])


def test_never_full_value_without_force_keeps_pesel_and_warns():
    text = f"PESEL {VALID_PESEL} należy do strony."
    findings, report = collect_findings_with_controls_report(text, {"never": [VALID_PESEL]})
    assert any(f.category == "PESEL" for f in findings)
    blocked = report["never"][0]["blocked_hard"]
    assert blocked.get("PESEL") == 1
    assert any("sumą kontrolną" in w for w in report["warnings"])


def test_never_with_force_unmasks_hard_category():
    text = f"PESEL {VALID_PESEL} należy do strony."
    findings, report = collect_findings_with_controls_report(text, {"never": [{"value": VALID_PESEL, "force": True}]})
    assert not any(f.category == "PESEL" for f in findings)
    assert report["never"][0]["suppressed"] >= 1


def test_always_person_rule_inherits_inflection_and_family():
    text = "Pismo doręczono Zenonowi Kowalskiemu. Zenon Kowalski podpisał."
    masked, reps = make_replacements_with_controls(text, {"always": [{"value": "Zenon Kowalski", "category": "OSOBA"}]})
    assert "Kowalskiemu" not in masked and "Kowalski podpisał" not in masked
    import re
    families = {m.group(1) for r in reps for m in [re.match(r"\[OSOBA_(\d+)", r.placeholder)] if m}
    assert families == {"1"}  # one identity family, not [MANUAL_n] + [OSOBA_n]
    assert not any(r.placeholder.startswith("[MANUAL") for r in reps)


def test_never_person_rule_covers_inflected_mentions():
    text = "Pełnomocnikiem jest r.pr. Anna Zielińska. Pismo doręczono Annie Zielińskiej."
    masked, _ = make_replacements_with_controls(text, {"never": ["Anna Zielińska"]})
    assert "Anna Zielińska" in masked
    assert "Annie Zielińskiej" in masked


def test_report_lists_dead_rules():
    _, report = collect_findings_with_controls_report(
        "Zwykły tekst bez danych osobowych.",
        {"always": [{"value": "Frazaniewystępująca", "category": "MANUAL"}], "never": ["inna fraza"]},
    )
    assert "Frazaniewystępująca" in report["dead_rules"]
    assert "inna fraza" in report["dead_rules"]


def test_rules_store_roundtrip_and_merge(tmp_path, monkeypatch):
    monkeypatch.setattr(rules_store, "RULES_DIR", tmp_path)
    rules_store.save_rules("global", {"never": ["Kancelaria Testowa"]})
    rules_store.save_rules("client", {"always": [{"value": "Projekt Feniks", "category": "PROJEKT"}]}, client_id="Spółka ABC")
    merged = rules_store.merge_controls({"always": [{"value": "Jan Testowy", "category": "OSOBA"}]}, client_id="Spółka ABC")
    always_values = {a["value"] for a in merged["always"]}
    assert {"Projekt Feniks", "Jan Testowy"} <= always_values
    assert "Kancelaria Testowa" in [n if isinstance(n, str) else n.get("value") for n in merged["never"]]
    assert rules_store.delete_rules("client", "Spółka ABC") is True
    assert rules_store.delete_rules("global") is True


def test_rules_endpoints_and_controls_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(rules_store, "RULES_DIR", tmp_path)
    original = base64.b64encode(_build_docx_with_revisions()).decode("ascii")
    prep = client.post("/v4/current/prepare", headers=HDR, json={"docx_base64": original, "filename": "umowa.docx", "open_file": False})
    assert prep.status_code == 200, prep.text
    prepared = prep.json()

    save = client.post("/v4/rules", headers=HDR, json={"level": "client", "client_id": "Spółka ABC", "controls": {"always": [{"value": "podpisał dokument", "category": "MANUAL"}]}})
    assert save.status_code == 200, save.text
    listed = client.get("/v4/rules", headers=HDR, params={"client_id": "Spółka ABC"})
    assert listed.status_code == 200
    assert len(listed.json()["client"]["always"]) == 1

    preview = client.post("/v4/controls/preview", headers=HDR, json={"map_id": prepared["map_id"], "client_id": "Spółka ABC", "controls": {"never": ["Jan Kowalski"]}})
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["controls_summary"]["always"] == 1  # merged from saved client rules
    assert body["controls_summary"]["never"] == 1
    never_effect = body["effects"]["never"][0]
    assert never_effect["suppressed"] >= 1
    assert never_effect["examples"]

    remask = client.post(
        "/v4/current/remask-session",
        headers=HDR,
        json={"map_id": prepared["map_id"], "session_id": prepared["session_id"], "filename": "umowa.docx", "open_file": False, "client_id": "Spółka ABC", "controls": {"never": ["Jan Kowalski"]}},
    )
    assert remask.status_code == 200, remask.text
    data = remask.json()
    assert data["controls_applied"] is True
    assert data["saved_rules"]["client_rules"] == 1
    assert data["controls_effects"]["never"][0]["value"] == "Jan Kowalski"

    deleted = client.post("/v4/rules/delete", headers=HDR, json={"level": "client", "client_id": "Spółka ABC"})
    assert deleted.status_code == 200 and deleted.json()["deleted"] is True
