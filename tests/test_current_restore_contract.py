import base64
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ["CSM_API_TOKEN"] = "test-token"
os.environ["CSM_DISABLE_OPEN_FILE"] = "1"

from api import app, _docx_remove_csm_metadata  # noqa: E402
from test_tracked_changes_preserve_mode import _build_docx_with_revisions  # noqa: E402

HDR = {"X-CSM-Token": "test-token"}
client = TestClient(app)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def test_v4_current_restore_without_metadata_but_with_map_id_restores_anon_docx():
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_bytes = Path(prepared["anon_path"]).read_bytes()

    # Simulate Word exposing the anonymized package without CSM customXml metadata.
    anon_without_metadata = _docx_remove_csm_metadata(anon_bytes)
    restore_response = client.post(
        "/v4/current/restore",
        headers=HDR,
        json={
            "docx_base64": _b64(anon_without_metadata),
            "filename": prepared["suggested_filename"],
            "map_id": prepared["map_id"],
            "session_id": prepared["session_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert restored["map_id"] == prepared["map_id"]
    assert restored["restore_report"]["restored_occurrences"] > 0
    assert Path(restored["restored_path"]).exists()


def test_v4_current_restore_original_doc_with_fallback_map_gets_actionable_error():
    original = _b64(_build_docx_with_revisions())
    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False},
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()

    restore_response = client.post(
        "/v4/current/restore",
        headers=HDR,
        json={
            "docx_base64": original,
            "filename": "umowa.docx",
            "map_id": prepared["map_id"],
            "open_file": False,
        },
    )
    assert restore_response.status_code == 400
    assert "oryginalnym pliku" in restore_response.text or "*_CSM_anon.docx" in restore_response.text


def test_v4_current_restore_without_metadata_and_without_map_gets_actionable_error():
    original = _b64(_build_docx_with_revisions())
    restore_response = client.post(
        "/v4/current/restore",
        headers=HDR,
        json={"docx_base64": original, "filename": "umowa.docx", "open_file": False},
    )
    assert restore_response.status_code == 400
    assert "Przełącz się" in restore_response.text or "*_CSM_anon.docx" in restore_response.text


def test_sanitize_error_detail_preserves_csm_document_names():
    """_CSM_anon.docx and _CSM_jawny.docx must survive _sanitize_error_detail.

    Regression for: the generic filename-redaction regex was replacing
    *_CSM_anon.docx with *<file-redacted>, making actionable error messages
    unreadable for the user.
    """
    from api import _sanitize_error_detail  # noqa: E402

    msg = (
        "Aktywny dokument nie zawiera metadanych CSM ani placeholderów z ostatniej mapy. "
        "Najpewniej przycisk wersji jawnej został użyty w oryginalnym pliku, a nie w kopii "
        "*_CSM_anon.docx. Przełącz się do zanonimizowanego dokumentu CSM i ponów operację."
    )
    sanitised = _sanitize_error_detail(msg)
    assert "_CSM_anon.docx" in sanitised, (
        f"_CSM_anon.docx was redacted. Got: {sanitised!r}"
    )

    msg2 = "Wersja jawna już istnieje jako *_CSM_jawny.docx. Nie twórz jej ponownie."
    sanitised2 = _sanitize_error_detail(msg2)
    assert "_CSM_jawny.docx" in sanitised2, (
        f"_CSM_jawny.docx was redacted. Got: {sanitised2!r}"
    )

    # Arbitrary user filenames must still be redacted.
    msg3 = "Nie można otworzyć pliku Jan_Kowalski_umowa.docx."
    sanitised3 = _sanitize_error_detail(msg3)
    assert "Jan_Kowalski_umowa.docx" not in sanitised3, (
        f"PII filename was NOT redacted. Got: {sanitised3!r}"
    )



def test_prepare_opens_anon_then_closes_source_document(monkeypatch, tmp_path):
    """One-document UX: after prepare opens *_CSM_anon.docx, backend closes the source Word doc."""
    import api  # noqa: E402

    original_bytes = _build_docx_with_revisions()
    source_path = tmp_path / "umowa.docx"
    source_path.write_bytes(original_bytes)
    closed = []

    monkeypatch.setattr(api, "_open_file_path", lambda path, enabled=True: (True, None))

    def fake_close_async(doc_path="", delay_sec=3.5, *, save_mode="save_then_close", doc_name=None, attempts=5):
        closed.append((str(doc_path), save_mode, doc_name))

    monkeypatch.setattr(api, "_close_word_document_async", fake_close_async)

    response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={
            "docx_base64": _b64(original_bytes),
            "filename": "umowa.docx",
            "open_file": True,
            "word_source_path": str(source_path),
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["opened_file"] is True
    assert data["suggested_filename"].endswith("_CSM_anon.docx")
    assert (str(source_path), "save_then_close", "umowa.docx") in closed
    assert response.json()["word_close_report"]["scheduled"] is True


def test_restore_opens_jawny_then_closes_anon_document(monkeypatch, tmp_path):
    """One-document UX: after restore opens jawny/original doc, backend closes *_CSM_anon.docx."""
    import api  # noqa: E402

    original_bytes = _build_docx_with_revisions()
    source_path = tmp_path / "umowa.docx"
    source_path.write_bytes(original_bytes)
    closed = []

    monkeypatch.setattr(api, "_open_file_path", lambda path, enabled=True: (True, None))

    def fake_close_async(doc_path="", delay_sec=3.5, *, save_mode="save_then_close", doc_name=None, attempts=5):
        closed.append((str(doc_path), save_mode, doc_name))

    monkeypatch.setattr(api, "_close_word_document_async", fake_close_async)
    monkeypatch.setattr(api, "_close_word_document", lambda *args, **kwargs: (True, None))

    prepare_response = client.post(
        "/v4/current/prepare",
        headers=HDR,
        json={
            "docx_base64": _b64(original_bytes),
            "filename": "umowa.docx",
            "open_file": True,
            "word_source_path": str(source_path),
        },
    )
    assert prepare_response.status_code == 200, prepare_response.text
    prepared = prepare_response.json()
    anon_path = Path(prepared["anon_path"])
    anon_bytes = anon_path.read_bytes()
    closed.clear()

    restore_response = client.post(
        "/v4/current/restore",
        headers=HDR,
        json={
            "docx_base64": _b64(anon_bytes),
            "filename": prepared["suggested_filename"],
            "open_file": True,
            "word_anon_path": str(anon_path),
        },
    )
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    assert restored["opened_file"] is True
    assert (str(anon_path), "discard_without_recovery", prepared["suggested_filename"]) in closed
    assert restored["word_close_report"]["scheduled"] is True


def test_word_close_helper_uses_sta_retry_and_unique_filename_fallback():
    api_text = (ROOT / "server" / "api.py").read_text(encoding="utf-8")
    assert '"-Sta"' in api_text
    assert "SourceName" in api_text
    assert "unique-name" in api_text
    assert "CSM_AMBIGUOUS_NAME_MATCH" in api_text
    assert "attempts: int = 5" in api_text


def test_taskpane_sends_filename_fallbacks_for_word_close():
    taskpane = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "word_source_name: filename || undefined" in taskpane
    assert "word_anon_name: currentName || undefined" in taskpane
    assert "word_anon_name: options.wordAnonName || undefined" in taskpane
    assert "describeWordCloseReport" in taskpane
