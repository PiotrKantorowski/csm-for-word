import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
os.environ.setdefault("CSM_API_TOKEN", "test-token")

from api import _docx_upsert_csm_metadata, _extract_csm_metadata  # noqa: E402
from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # type: ignore  # noqa: E402

pytestmark = pytest.mark.future


def test_future_csm_metadata_schema_tolerates_additive_fields():
    """Forward-compatible metadata changes must not break restore detection.

    Planned session metadata can add fields in later releases, but v0.4 clients
    still need to read the map/session identifiers required for restore.
    """
    docx = _build_docx_with_revisions()
    with_metadata = _docx_upsert_csm_metadata(docx, {
        "map_id": "future-map-id",
        "session_id": "future-session-id",
        "csm_document_kind": "anon",
        "planned_schema_version": "2",
        "future.extra.flag": "enabled",
    })

    metadata = _extract_csm_metadata(with_metadata)

    assert metadata["map_id"] == "future-map-id"
    assert metadata["session_id"] == "future-session-id"
    assert metadata["csm_document_kind"] == "anon"
    assert metadata["planned_schema_version"] == "2"
    assert metadata["future.extra.flag"] == "enabled"
