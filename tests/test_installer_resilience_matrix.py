from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_runtime_requirements_avoid_optional_native_uvicorn_standard_stack() -> None:
    req = read("server/requirements-runtime.txt")
    assert "uvicorn==0.34.0" in req
    assert "uvicorn[standard]" not in req
    assert "pytest" not in req
    assert "httpx" not in req


def test_setup_has_multi_path_python312_bootstrap_and_binary_only_install() -> None:
    text = read("tools/setup-once.ps1")
    assert "Python.Python.3.12" in text
    assert "python-$RecommendedPythonVersion-amd64.exe" in text
    assert "WindowsApps" in text
    assert "Get-PythonCandidates" in text
    assert "--only-binary=:all:" in text
    assert "--prefer-binary" in text
    assert "Info.Minor -ne 12" in text
    assert "cp312" in text
    assert "3.10-3.13" not in text
    assert "Node/npm" not in text
    assert "npx" not in text.lower()


def test_autostart_has_compatibility_fallbacks_for_windows_scheduled_tasks() -> None:
    text = read("tools/register-autostart.ps1")
    assert "-RunLevel Limited" in text
    assert "LeastPrivilege" not in text
    assert "try { $trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId }" in text
    assert "Ostrzezenie: standardowa rejestracja zadania nie powiodla sie" in text
    assert "DisallowStartIfOnBatteries" in text


def test_diagnostics_tool_exists_and_checks_core_failure_points() -> None:
    text = read("tools/diagnose-csm.ps1")
    assert "CSM diagnostic" in text
    assert "Python w systemie" in text
    assert "Porty i procesy" in text
    assert "HTTP lokalne" in text
    assert "Certyfikat localhost" in text
    assert "Word TrustedCatalogs" in text
    assert "https://localhost:3000/taskpane.html" in text
    assert (ROOT / "tools" / "CSM-DIAGNOZA.cmd").exists()


def test_start_does_not_kill_unrelated_port_owners() -> None:
    text = read("tools/start-claude-safe-mode.ps1")
    assert "Test-CsmOwnedProcess" in text
    assert "Port $Port jest zajety przez inny proces" in text
    assert "Zatrzymuje stary proces CSM" in text


def test_installer_runs_diagnostics_when_start_after_install_fails() -> None:
    text = read("tools/install-csm.ps1")
    assert "diagnose-csm.ps1" in text
    assert "Uruchamiam szybka diagnostyke CSM" in text
    assert "CSM -> DIAGNOZA" in text


def test_setup_does_not_parse_join_path_localappdata_as_array_childpath() -> None:
    text = read("tools/setup-once.ps1")
    assert "$localPythonRoot" in text
    assert "Join-Path -Path ([string]$env:LOCALAPPDATA) -ChildPath \"Programs\\Python\"" in text
    assert "Join-Path $env:LOCALAPPDATA \"Programs\\Python\"," not in text


def test_user_facing_support_contact_is_present_in_install_and_panels() -> None:
    expected = "csm@kancelariakantorowski.pl"
    for rel in [
        "ZAINSTALUJ_CSM.cmd",
        "tools/install-csm.ps1",
        "tools/setup-once.ps1",
        "tools/start-claude-safe-mode.ps1",
        "tools/diagnose-csm.ps1",
        "tools/CSM.ps1",
        "tools/CSM.cmd",
        "addin/taskpane.html",
        "addin/taskpane.js",
    ]:
        assert expected in read(rel), rel


def test_taskpane_danger_notices_append_support_hint() -> None:
    text = read("addin/taskpane.js")
    assert "const SUPPORT_EMAIL" in text
    assert "function withSupportHint" in text
    assert "const finalText = withSupportHint(type, text);" in text
    assert "setStatus(message, includeSupport = false)" in text
