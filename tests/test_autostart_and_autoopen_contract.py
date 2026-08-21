from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_uses_office_auto_show_taskpane_id() -> None:
    manifest = (ROOT / "addin" / "manifest.xml").read_text(encoding="utf-8")
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "<TaskpaneId>Office.AutoShowTaskpaneWithDocument</TaskpaneId>" in manifest
    assert "<TaskpaneId>ClaudeSafeMode.Taskpane</TaskpaneId>" not in manifest
    assert "Office.AutoShowTaskpaneWithDocument" in js


def test_start_script_supports_noninteractive_autostart_mode() -> None:
    start = (ROOT / "tools" / "start-claude-safe-mode.ps1").read_text(encoding="utf-8")
    assert "[switch]$NoOpenWord" in start
    assert "[switch]$NonInteractive" in start
    assert "if (-not $NonInteractive)" in start
    assert "if ($NoOpenWord)" in start
    assert "Start-Process winword" in start


def test_installer_registers_user_logon_scheduled_task() -> None:
    installer = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    register = (ROOT / "tools" / "register-autostart.ps1").read_text(encoding="utf-8")
    unregister = (ROOT / "tools" / "unregister-autostart.ps1").read_text(encoding="utf-8")
    uninstall = (ROOT / "tools" / "uninstall-csm.ps1").read_text(encoding="utf-8")

    assert "[switch]$NoAutostart" in installer
    assert "function Enable-Autostart" in installer
    assert "register-autostart.ps1" in installer
    assert "-NoOpenWord -NonInteractive" in installer
    assert "CSM AutoStart" in register
    assert "[System.Security.Principal.WindowsIdentity]::GetCurrent().Name" in register
    assert "New-ScheduledTaskTrigger -AtLogOn -User $UserId" in register
    assert "-NoOpenWord -NonInteractive" in register
    assert "Register-ScheduledTask" in register
    assert "Unregister-ScheduledTask" in unregister
    assert "KnownTaskNames" in unregister
    assert "start-claude-safe-mode\\.ps1" in unregister
    assert "Autostart CSM nie byl zarejestrowany - OK" in unregister
    assert "[switch]$AllowMissing" in unregister
    assert "unregister-autostart.ps1" in uninstall


def test_panel_autostarts_background_services_on_open() -> None:
    panel = (ROOT / "tools" / "CSM.ps1").read_text(encoding="utf-8")
    assert "otwarcie panelu CSM samo uruchamia START" in panel
    assert "START - uruchom CSM w tle" in panel
    assert "function Start-CsmAutomaticallyOnOpen" in panel
    assert "$form.Add_Shown({ Start-CsmAutomaticallyOnOpen })" in panel
    assert "Test-CsmAlreadyRunning" in panel
    assert 'Start-CsmScript -ScriptName "start-claude-safe-mode.ps1" -Label "CSM - AUTO START" -ExtraArgs @("-NoOpenWord", "-NonInteractive") -Hidden' in panel
    assert '-ExtraArgs @("-NoOpenWord", "-NonInteractive")' in panel


def test_clean_restart_keeps_background_mode() -> None:
    clean = (ROOT / "tools" / "CSM-CLEAN.ps1").read_text(encoding="utf-8")
    assert "[string[]]$ExtraArgs = @()" in clean
    assert 'Start-ScriptIfExists -ScriptName "start-claude-safe-mode.ps1" -Label "CSM - START" -ExtraArgs @("-NoOpenWord", "-NonInteractive")' in clean
    assert "CSM zostal ponownie uruchomiony w tle" in clean


def test_uninstall_preserves_original_user_profile_cleanup_after_uac() -> None:
    uninstall = (ROOT / "tools" / "uninstall-csm.ps1").read_text(encoding="utf-8")
    assert "[switch]$ElevatedPhase" in uninstall
    assert "function Remove-UserProfileArtifacts" in uninstall
    assert "function Remove-MachineArtifacts" in uninstall
    assert '"-OriginalDesktop", "`"$OriginalDesktop`""' in uninstall
    assert '"-OriginalLocalAppData", "`"$OriginalLocalAppData`""' in uninstall
    assert 'Start-Process -FilePath "powershell.exe" -ArgumentList $args -Verb RunAs -Wait -PassThru' in uninstall
    assert "Remove-UserProfileArtifacts -DesktopPath $OriginalDesktop -LocalAppDataPath $OriginalLocalAppData" in uninstall
    assert "HKCU:\\Software\\Microsoft\\Office\\16.0\\WEF\\TrustedCatalogs" in uninstall


def test_legacy_start_cmd_uses_background_mode() -> None:
    cmd = (ROOT / "tools" / "start-claude-safe-mode.cmd").read_text(encoding="utf-8")
    assert "-NoOpenWord -NonInteractive" in cmd


def test_uninstall_removes_autostart_once_in_machine_phase() -> None:
    uninstall = (ROOT / "tools" / "uninstall-csm.ps1").read_text(encoding="utf-8")
    assert uninstall.count("unregister-autostart.ps1") == 1
    assert "Autostart is a Task Scheduler artifact" in uninstall
    assert "Remove-MachineArtifacts" in uninstall
    assert "-InstallDir $InstallDir -AllowMissing" in uninstall


def test_unregistered_autostart_message_is_neutral_and_legacy_names_are_removed() -> None:
    unregister = (ROOT / "tools" / "unregister-autostart.ps1").read_text(encoding="utf-8")
    assert "Claude Safe Mode AutoStart" in unregister
    assert "ClaudeSafeMode AutoStart" in unregister
    assert "Autostart CSM nie byl zarejestrowany - OK, nie ma czego usuwac." in unregister
    assert "DarkGray" in unregister
    assert "Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object" in unregister
