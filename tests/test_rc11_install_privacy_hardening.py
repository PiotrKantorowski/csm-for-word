import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import redactor
from redactor import Replacement, save_map, load_install_backup, make_replacements


def test_install_backups_store_protected_payload_not_plaintext_files(tmp_path, monkeypatch):
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(redactor, "INSTALL_BACKUPS_DIR", backup_dir)
    monkeypatch.setattr(redactor, "MAPS_DIR", tmp_path / "maps")
    map_id = save_map(
        [Replacement(category="PERSON", original="Jan Kowalski", placeholder="[OSOBA_1]", count=1)],
        original_text="Poufny Jan Kowalski",
        original_ooxml="<w:t>Jan Kowalski</w:t>",
        original_docx_base64="UEsDBAoAAAAAA",
        require_install_backup=True,
    )
    bdir = backup_dir / map_id
    assert (bdir / "backup_payload.csmmap").exists()
    manifest = json.loads((bdir / "backup_manifest.json").read_text(encoding="utf-8"))
    assert manifest["protected_payload"] is True
    assert manifest["payload_file"] == "backup_payload.csmmap"
    for name in (
        "original_visible_text.txt",
        "original_ooxml.xml",
        "original_ooxml_parts.json",
        "original_docx_base64.txt",
        "original_document.docx",
    ):
        assert not (bdir / name).exists(), name
    loaded = load_install_backup(map_id)
    assert loaded["original_text"] == "Poufny Jan Kowalski"
    assert loaded["original_ooxml"] == "<w:t>Jan Kowalski</w:t>"
    assert loaded["original_docx_base64"] == "UEsDBAoAAAAAA"


def test_setup_once_supports_local_wheelhouse_before_pypi():
    script = (ROOT / "tools" / "setup-once.ps1").read_text(encoding="utf-8")
    assert "$WheelhouseDir" in script
    assert "Get-WheelhousePipArgs" in script
    assert "--no-index" in script
    assert "--find-links" in script
    assert "Instaluje bez pobierania z internetu" in script


def test_reversible_pseudonymization_keeps_common_word_entities_roundtrip_safe():
    text = (
        "Działając w imieniu Klienta – OLIMP LABORATORIES, Pustynia 84F, 39-200 Dębica, "
        "na rzecz Pani Iwony Teresy Ustrzyckiej (PESEL: 90010112345), "
        "Jan Mucha prowadzi firmę Meble New Concept."
    )
    masked, replacements = make_replacements(text)
    assert "OLIMP LABORATORIES" not in masked
    assert "Pustynia 84F" not in masked
    assert "Iwony Teresy Ustrzyckiej" not in masked
    assert "Jan Mucha" not in masked
    assert "Meble New Concept" not in masked
    restored = masked
    for r in sorted(replacements, key=lambda item: len(item.placeholder), reverse=True):
        restored = restored.replace(r.placeholder, r.original)
    assert restored == text
