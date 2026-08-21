from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_setup_python_candidate_join_path_is_parenthesized_without_comma_bug() -> None:
    text = read("tools/setup-once.ps1")
    assert 'Join-Path $env:LOCALAPPDATA "Programs\\Python",' not in text
    assert '$localPythonRoot = if ($env:LOCALAPPDATA)' in text
    assert 'Join-Path -Path ([string]$env:LOCALAPPDATA) -ChildPath "Programs\\Python"' in text


def test_install_and_setup_errors_show_support_contact() -> None:
    install = read("tools/install-csm.ps1")
    setup = read("tools/setup-once.ps1")
    assert "csm@kancelariakantorowski.pl" in install
    assert "csm@kancelariakantorowski.pl" in setup
    assert "$script:CsmInstallTrapActive" in install
    assert "$script:CsmSetupTrapActive" in setup
    assert "Write-SupportHint" in install
    assert "Write-SupportHint" in setup


def test_word_panel_and_desktop_panel_have_permanent_support_contact() -> None:
    html = read("addin/taskpane.html")
    js = read("addin/taskpane.js")
    desktop = read("tools/CSM.ps1")
    assert "mailto:csm@kancelariakantorowski.pl" in html
    assert "support-card" in html
    assert "SUPPORT_HINT" in js
    assert "withSupportHint" in js
    assert "csm@kancelariakantorowski.pl" in desktop
