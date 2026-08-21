"""
Tests for open-source gazetteer infrastructure and license policy compliance.

Verifies:
- licenses.json exists and is valid
- All bundled sources have acceptable licenses
- verify_gazetteer_licenses.py exits 0
- Sample gazetteer files exist and are valid JSON
- build_pl_gazetteers.py is importable and --dry-run works
- docs policy files exist
- pl_gazetteers.py exposes expected sets
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GAZETTEERS_DIR = ROOT / "server" / "gazetteers"
LICENSES_PATH = GAZETTEERS_DIR / "licenses.json"

# ---------------------------------------------------------------------------
# licenses.json structure
# ---------------------------------------------------------------------------

def test_licenses_json_exists_and_is_valid():
    assert LICENSES_PATH.exists(), f"Missing: {LICENSES_PATH}"
    data = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    assert data.get("schema_version") == 1
    assert "generated_at" in data
    assert isinstance(data.get("sources"), list)
    assert len(data["sources"]) >= 3, "Expected at least 3 source entries"


def test_licenses_json_all_bundled_have_required_fields():
    data = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    required_fields = {"id", "name", "url", "license", "license_url", "downloaded_at", "bundled", "allowed_for_runtime"}
    for source in data.get("sources", []):
        if source.get("bundled"):
            missing = required_fields - set(source.keys())
            assert not missing, f"Source {source.get('id')!r} missing fields: {missing}"


def test_licenses_json_no_forbidden_licenses_in_bundled():
    FORBIDDEN = {"unknown", "research-only", "non-commercial", "no-redistribution", "restricted"}
    data = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    for source in data.get("sources", []):
        if source.get("bundled"):
            lic = source.get("license", "").lower()
            assert lic not in FORBIDDEN, (
                f"Source {source.get('id')!r} has forbidden license: {source.get('license')!r}"
            )


def test_licenses_json_bundled_sources_allowed_for_runtime():
    data = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    for source in data.get("sources", []):
        if source.get("bundled"):
            assert source.get("allowed_for_runtime") is True, (
                f"Bundled source {source.get('id')!r} has allowed_for_runtime != true"
            )


def test_licenses_json_proprietary_only_for_internal_url():
    data = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    for source in data.get("sources", []):
        if source.get("bundled") and source.get("license") == "proprietary":
            assert source.get("url") == "internal", (
                f"Source {source.get('id')!r}: 'proprietary' license only valid for url='internal'"
            )


def test_licenses_json_rejected_sources_have_reason():
    data = json.loads(LICENSES_PATH.read_text(encoding="utf-8"))
    for source in data.get("rejected_sources", []):
        assert "reason_rejected" in source, f"Rejected source {source.get('id')!r} missing 'reason_rejected'"
        assert source.get("bundled") is not True, (
            f"Rejected source {source.get('id')!r} must not have bundled=true"
        )


# ---------------------------------------------------------------------------
# verify_gazetteer_licenses.py tool
# ---------------------------------------------------------------------------

def test_verify_gazetteer_licenses_exits_zero():
    result = subprocess.run(
        [sys.executable, "tools/verify_gazetteer_licenses.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"verify_gazetteer_licenses.py failed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


# ---------------------------------------------------------------------------
# Sample gazetteer files
# ---------------------------------------------------------------------------

SAMPLE_FILES = [
    "pl_first_names.sample.json",
    "pl_surnames.sample.json",
    "pl_places.sample.json",
    "pl_streets.sample.json",
    "pl_common_words_negative.sample.json",
    "pl_legal_labels_negative.json",
]

def test_sample_gazetteer_files_exist():
    for fname in SAMPLE_FILES:
        path = GAZETTEERS_DIR / fname
        assert path.exists(), f"Missing sample file: {path}"


def test_sample_gazetteer_files_valid_json():
    for fname in SAMPLE_FILES:
        path = GAZETTEERS_DIR / fname
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            assert False, f"Invalid JSON in {path}: {exc}"
        assert data.get("schema_version") == 1, f"{path} missing or wrong schema_version"


def test_legal_labels_negative_has_entries():
    path = GAZETTEERS_DIR / "pl_legal_labels_negative.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    assert len(entries) >= 20, f"Expected >= 20 legal label negatives, got {len(entries)}"
    # Spot check key entries
    for required in ["dane klienta", "nazwa spółki", "adres siedziby", "numer umowy", "data umowy"]:
        assert required in entries, f"Missing required label negative: {required!r}"


def test_common_words_negative_has_known_words():
    path = GAZETTEERS_DIR / "pl_common_words_negative.sample.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    words = {e["word"] for e in entries}
    for required in ["mucha", "lis", "wilk", "kot", "baran"]:
        assert required in words, f"Missing common-word negative: {required!r}"


def test_first_names_sample_has_known_names():
    path = GAZETTEERS_DIR / "pl_first_names.sample.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    assert len(entries) >= 20
    assert "Jan" in entries
    assert "Anna" in entries


def test_places_sample_has_pustynia():
    path = GAZETTEERS_DIR / "pl_places.sample.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    entries = data.get("entries", [])
    nominatives = {e["nominative"] for e in entries}
    genitives = {e["genitive"] for e in entries}
    assert "Pustynia" in nominatives
    assert "Pustyni" in genitives


# ---------------------------------------------------------------------------
# build_pl_gazetteers.py tool — dry-run
# ---------------------------------------------------------------------------

def test_build_pl_gazetteers_dry_run_exits_zero():
    result = subprocess.run(
        [sys.executable, "tools/build_pl_gazetteers.py", "--source", "all", "--dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"build_pl_gazetteers.py --dry-run failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "Done." in result.stdout


# ---------------------------------------------------------------------------
# docs policy files
# ---------------------------------------------------------------------------

def test_open_source_sources_doc_exists():
    path = ROOT / "docs" / "OPEN_SOURCE_PL_ANONYMIZATION_SOURCES.md"
    assert path.exists(), f"Missing: {path}"
    text = path.read_text(encoding="utf-8")
    assert "CC0" in text
    assert "dane.gov.pl" in text
    assert "PESEL" in text


def test_pseudonymization_resource_policy_doc_exists():
    path = ROOT / "docs" / "PL_PSEUDONYMIZATION_RESOURCE_POLICY.md"
    assert path.exists(), f"Missing: {path}"
    text = path.read_text(encoding="utf-8")
    assert "context_score" in text
    assert "negative_score" in text
    assert "No blind gazetteer masking" in text or "blind" in text


# ---------------------------------------------------------------------------
# pl_gazetteers.py runtime sets
# ---------------------------------------------------------------------------

def test_pl_gazetteers_exports_expected_sets():
    sys.path.insert(0, str(ROOT / "server"))
    import importlib
    gaz = importlib.import_module("pl_gazetteers")
    importlib.reload(gaz)
    assert hasattr(gaz, "FIRST_NAMES"), "pl_gazetteers missing FIRST_NAMES"
    assert hasattr(gaz, "SURNAMES"), "pl_gazetteers missing SURNAMES"
    assert hasattr(gaz, "LOCALITIES"), "pl_gazetteers missing LOCALITIES"
    assert len(gaz.FIRST_NAMES) >= 1000
    assert len(gaz.SURNAMES) >= 1000
    assert len(gaz.LOCALITIES) >= 10000


def test_pl_gazetteers_first_names_contain_known_names():
    sys.path.insert(0, str(ROOT / "server"))
    import importlib
    gaz = importlib.import_module("pl_gazetteers")
    for name in ["Jan", "Anna", "Maria", "Piotr", "Tomasz", "Agnieszka"]:
        assert name in gaz.FIRST_NAMES, f"FIRST_NAMES missing expected name: {name!r}"


def test_pl_gazetteers_surnames_contain_known_surnames():
    sys.path.insert(0, str(ROOT / "server"))
    import importlib
    gaz = importlib.import_module("pl_gazetteers")
    for surname in ["Kowalski", "Nowak", "Wiśniewski", "Dąbrowski", "Lewandowski"]:
        assert surname in gaz.SURNAMES, f"SURNAMES missing expected surname: {surname!r}"


def test_pl_gazetteers_localities_contain_pustynia_forms():
    sys.path.insert(0, str(ROOT / "server"))
    import importlib
    gaz = importlib.import_module("pl_gazetteers")
    assert "Pustynia" in gaz.LOCALITIES, "LOCALITIES missing 'Pustynia'"
    assert "Pustyni" in gaz.LOCALITIES, "LOCALITIES missing genitive 'Pustyni'"
