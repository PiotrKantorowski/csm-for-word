from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ["CSM_API_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402
from api import app  # noqa: E402
from word_revision_engine import (  # noqa: E402
    CSM_REVISION_MAP_NS,
    build_custom_xml_payload,
    build_document_metadata,
    build_revision_job,
    select_restore_strategy,
    summarize_revision_job,
    validate_revision_job,
)

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)


def test_revision_engine_builds_restore_plan_from_replacements_and_anchors():
    job = build_revision_job(
        map_id="map-1",
        mode="restore",
        replacements=[{"category": "PERSON", "original": "Adam Kowalski", "placeholder": "[[CSM_PERSON_1]]"}],
        anchors=[{"anchorId": "CSM_ANCHOR:a1", "currentText": "[[CSM_PERSON_1]]", "originalText": "Adam Kowalski", "trackedChangeCount": 1}],
    )
    assert job.operations[0].from_text == "[[CSM_PERSON_1]]"
    assert job.operations[0].to_text == "Adam Kowalski"
    assert job.operations[0].anchor_id == "CSM_ANCHOR:a1"
    summary = summarize_revision_job(job)
    assert summary["operations_count"] == 1
    assert summary["anchored_operations_count"] == 1
    assert summary["tracked_anchors_count"] == 1
    assert summary["sidecar_required"] is True
    assert summary["restore_strategy"]["mode"] == "range-ooxml"
    validation = validate_revision_job(job)
    assert validation["ok"] is True
    assert any(issue["code"] == "sidecar_not_available" for issue in validation["issues"])


def test_revision_engine_builds_anonymize_plan_and_custom_xml_payload():
    job = build_revision_job(
        map_id="map-2",
        mode="anonymize",
        replacements=[{"category": "EMAIL", "original": "adam@example.com", "placeholder": "[[CSM_EMAIL_1]]"}],
        anchors=[{"anchor_id": "CSM_ANCHOR:e1", "current_text": "adam@example.com", "entity_type": "EMAIL"}],
    )
    assert job.operations[0].from_text == "adam@example.com"
    assert job.operations[0].to_text == "[[CSM_EMAIL_1]]"
    xml = build_custom_xml_payload(job)
    assert CSM_REVISION_MAP_NS in xml
    assert "map-2" in xml
    assert "CSM_ANCHOR:e1" in xml
    assert "adam@example.com" in xml
    assert "[[CSM_EMAIL_1]]" in xml
    assert "<csm:strategy" in xml


def test_revision_plan_endpoint_returns_restore_contract_without_sidecar_execution():
    r = client.post(
        "/v2/revision/restore",
        headers=HDR,
        json={
            "map_id": "map-endpoint",
            "replacements": [{"category": "PERSON", "original": "Jan Nowak", "placeholder": "[[CSM_PERSON_7]]"}],
            "anchors": [{"anchorId": "CSM_ANCHOR:p7", "currentText": "[[CSM_PERSON_7]]", "trackedChangeCount": 1}],
            "keep_tracking": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["version"] == "1.6"
    assert data["engine_version"] == "0.5.2-revision-plan"
    assert data["namespace"] == CSM_REVISION_MAP_NS
    assert data["summary"]["operations_count"] == 1
    assert data["summary"]["sidecar_available"] is False
    assert data["strategy"]["mode"] == "range-ooxml"
    assert data["operations"][0]["from_text"] == "[[CSM_PERSON_7]]"
    assert data["operations"][0]["to_text"] == "Jan Nowak"
    assert "custom_xml_payload" in data
    assert "document_metadata" in data
    assert data["document_metadata"]["CSM_RevisionMapId"] == "map-endpoint"
    assert data["document_metadata"]["CSM_RevisionMapNamespace"] == CSM_REVISION_MAP_NS


def test_revision_validate_reports_unanchored_operations_as_fallback_risk():
    r = client.post(
        "/v2/revision/validate",
        headers=HDR,
        json={
            "mode": "restore",
            "replacements": [{"category": "PERSON", "original": "Jan Nowak", "placeholder": "[[CSM_PERSON_7]]"}],
            "anchors": [],
            "keep_tracking": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["summary"]["unanchored_operations_count"] == 1
    assert any(issue["code"] == "unanchored_operation" for issue in data["validation"]["issues"])


def test_revision_engine_builds_document_metadata_for_settings_and_properties():
    job = build_revision_job(
        map_id="map-meta",
        mode="restore",
        replacements=[{"category": "PERSON", "original": "Anna", "placeholder": "[[CSM_PERSON_1]]"}],
    )
    metadata = build_document_metadata(job, custom_xml_part_id="xml-part-1")
    assert metadata["CSM_RevisionMapPartId"] == "xml-part-1"
    assert metadata["CSM_RevisionMapId"] == "map-meta"
    assert metadata["CSM_RevisionMapSchemaVersion"] == "0.5.2-revision-map"
    assert metadata["CSM_RevisionEngineVersion"] == "0.5.2-revision-plan"
    assert metadata["CSM_RevisionMapNamespace"] == CSM_REVISION_MAP_NS
    assert metadata["CSM_RevisionOperationsCount"] == "1"
    assert metadata["CSM_RevisionAnchorsCount"] == "0"
    assert metadata["CSM_RevisionRestoreStrategy"] == "text-fallback"


def test_revision_engine_selects_paragraph_strategy_for_multiple_ops_in_same_paragraph():
    job = build_revision_job(
        map_id="map-paragraph",
        mode="restore",
        replacements=[
            {"category": "PERSON", "original": "Anna", "placeholder": "[[CSM_PERSON_1]]"},
            {"category": "PERSON", "original": "Jan", "placeholder": "[[CSM_PERSON_2]]"},
        ],
        anchors=[
            {"anchorId": "CSM_ANCHOR:a1", "currentText": "[[CSM_PERSON_1]]", "paragraphId": "p1"},
            {"anchorId": "CSM_ANCHOR:a2", "currentText": "[[CSM_PERSON_2]]", "paragraphId": "p1"},
        ],
    )
    strategy = select_restore_strategy(job)
    assert strategy.mode == "paragraph-ooxml"
    assert strategy.operations_scope == "paragraph"
    assert summarize_revision_job(job)["restore_strategy"]["mode"] == "paragraph-ooxml"


def test_revision_engine_selects_full_docx_strategy_for_non_body_parts():
    job = build_revision_job(
        map_id="map-header",
        mode="restore",
        replacements=[{"category": "PERSON", "original": "Anna", "placeholder": "[[CSM_PERSON_1]]"}],
        anchors=[{"anchorId": "CSM_ANCHOR:h1", "currentText": "[[CSM_PERSON_1]]", "sourcePart": "word/header1.xml"}],
    )
    strategy = select_restore_strategy(job)
    assert strategy.mode == "full-docx"
    assert strategy.requires_full_package is True
    validation = validate_revision_job(job)
    assert validation["ok"] is True
    assert any(issue["code"] == "sidecar_not_available" for issue in validation["issues"])


def test_revision_plan_endpoint_returns_404_for_missing_map_instead_of_500():
    for endpoint in ["/v2/revision/restore", "/v2/revision/anonymize", "/v2/revision/validate"]:
        r = client.post(endpoint, headers=HDR, json={"map_id": "missing-map-for-hardening"})
        assert r.status_code == 404, (endpoint, r.status_code, r.text)
        assert "mapy rewizyjnej" in r.text or "Revision map" in r.text
