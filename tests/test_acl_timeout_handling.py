from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")


def test_install_acl_step_uses_timeout_and_no_recursive_root_grant() -> None:
    assert "Invoke-NativeTimed" in INSTALLER
    assert "TIMEOUT after $TimeoutSeconds seconds" in INSTALLER
    assert "Pomijam wolne rekurencyjne icacls /T" in INSTALLER
    assert "Grant-PathAccessFast" in INSTALLER
    assert "Instalacja idzie dalej" in INSTALLER

    # The old failure path was a recursive icacls over the whole C:\\CSM tree.
    # That can hang on old sessions/backups and then return 0xC000013A when closed.
    assert not re.search(r"icacls\.exe\s+\$InstallDir[^\n]*/T", INSTALLER)
    assert not re.search(r"icacls\.exe\s+\$AddinDir[^\n]*/T", INSTALLER)


def test_install_acl_targets_only_runtime_paths_needed_after_elevation() -> None:
    assert '"runtime", "sessions", "backups", "addin", "server\\audit"' in INSTALLER
    assert '"*${OriginalUserSid}:(OI)(CI)M"' in INSTALLER
    assert '"*S-1-1-0:(OI)(CI)RX"' in INSTALLER
    assert 'Grant-PathAccessFast -Path $AddinDir' in INSTALLER
