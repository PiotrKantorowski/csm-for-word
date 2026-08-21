from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tests" / "fixtures" / "public_sources_raw" / "manifest.json"


def test_public_source_manifest_is_bundled_and_complete():
    assert MANIFEST.exists(), "public source manifest must be bundled for benchmark traceability"
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(entries) >= 6
    assert {entry["name"] for entry in entries} >= {
        "gov_vehicle_sale_pdf",
        "gov_vehicle_sale_pdf_alt",
        "gov_power_of_attorney",
        "gov_commercial_lease",
        "senat_commercial_lease_doc",
        "so_warszawa_response_to_claim_doc",
    }


def test_public_source_manifest_files_match_sha256():
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for entry in entries:
        path = ROOT / entry["file"]
        assert path.exists(), f"missing bundled public source: {entry['name']}"
        data = path.read_bytes()
        assert len(data) == entry["bytes"]
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
