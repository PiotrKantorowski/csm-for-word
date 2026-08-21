from pathlib import Path

from redactor import make_replacements

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _restore_plain(masked: str, replacements) -> str:
    restored = masked
    for r in sorted(replacements, key=lambda item: len(item.placeholder), reverse=True):
        restored = restored.replace(r.placeholder, r.original)
    return restored


def test_installer_child_steps_have_timeout_and_setup_once_log() -> None:
    install = read("tools/install-csm.ps1")
    setup = read("tools/setup-once.ps1")
    # setup-once.ps1 is invoked directly (streaming) so the user sees live pip/venv output.
    # Invoke-ChildPowerShellLoggedTimed is still used for start-claude-safe-mode.ps1 (120 s).
    assert "& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup" in install, \
        "Run-SetupOnce must call setup-once.ps1 directly so output streams to console"
    assert "CSM-setup-once.log" in install, \
        "Run-SetupOnce error message must reference the setup-once log path"
    assert "start-claude-safe-mode.ps1" in install and "-TimeoutSeconds 120" in install
    assert "Invoke-ChildPowerShellLoggedTimed" in install, \
        "Invoke-ChildPowerShellLoggedTimed must still be used for start-claude-safe-mode.ps1"
    assert "CSM-setup-once.log" in setup
    assert "przekroczyl limit czasu" in setup
    assert "Start-Process -FilePath $FilePath" in setup


def test_process_party_uppercase_company_without_suffix_is_masked() -> None:
    text = (
        "Działając w imieniu Klienta – OLIMP LABORATORIES, Pustynia 84F, 39-200 Dębica; "
        "wzywam Pana Jana Muchę do zapłaty."
    )
    masked, replacements = make_replacements(text)
    assert "OLIMP LABORATORIES" not in masked
    assert "Pustynia 84F" not in masked
    assert "Jana Muchę" not in masked
    assert any(r.category in {"CONTRACTOR", "COMPANY"} and r.original == "OLIMP LABORATORIES" for r in replacements)
    assert _restore_plain(masked, replacements) == text


def test_quoted_process_party_company_without_suffix_is_masked_and_reversible() -> None:
    text = 'Powód: "OLIMP LABORATORIES" z siedzibą w Pustyni, NIP: 1234567890.'
    masked, replacements = make_replacements(text)
    assert "OLIMP LABORATORIES" not in masked
    assert "Pustyni" not in masked
    assert "1234567890" not in masked
    assert _restore_plain(masked, replacements) == text


def test_do_not_mask_generic_uppercase_legal_heading_as_company() -> None:
    text = "WEZWANIE DO ZAPŁATY – OSTATECZNE PRZEDSĄDOWE"
    masked, replacements = make_replacements(text)
    assert masked == text
    assert replacements == []
