from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_single_visible_installer_and_tools_folder():
    assert (ROOT / "ZAINSTALUJ_CSM.cmd").exists()
    assert (ROOT / "tools" / "install-csm.ps1").exists()
    for rel in [
        "install-csm.ps1",
        "repair-csm.ps1",
        "uninstall-csm.ps1",
        "CSM.ps1",
        "CSM.cmd",
        "CSM-CLEAN.ps1",
        "NAPRAW_CSM.cmd",
        "ODINSTALUJ_CSM.cmd",
    ]:
        assert not (ROOT / rel).exists(), f"technical script should not be at root: {rel}"


def test_launcher_exposes_start_stop_clean_repair_uninstall_and_background_message():
    launcher = (ROOT / "tools" / "CSM.ps1").read_text(encoding="utf-8")
    assert "START - uruchom CSM w tle" in launcher
    assert "STOP - zatrzymaj CSM" in launcher
    assert "CLEAN - wyczysc cache Worda" in launcher
    assert "NAPRAW - odswiez instalacje" in launcher
    assert "ODINSTALUJ CSM" in launcher
    assert "dziala w tle po START" in launcher


def test_desktop_shortcut_points_to_tools_launcher():
    shortcut = (ROOT / "tools" / "create-desktop-shortcut.ps1").read_text(encoding="utf-8")
    assert "CSM.ps1" in shortcut
    assert "powershell.exe" in shortcut
    assert "NAPRAW, ODINSTALUJ" in shortcut


def test_readme_describes_one_click_installation():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "ZAINSTALUJ_CSM.cmd" in readme
    assert "jedną ikonę" in readme or "jedna ikona" in readme
    assert "CSM nadal będzie dostępny" in readme


def test_installer_separates_admin_and_user_profile_steps():
    installer = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    assert "ElevatedPhase" in installer
    assert "Invoke-ElevatedPhase" in installer
    assert "-Wait -PassThru" in installer
    assert "Add-TrustedCatalogRegistry" in installer
    # RC18: desktop shortcut removed from install flow — replaced by Word taskpane panel.
    # assert "-DesktopPath $OriginalDesktop" in installer  # removed in rc18
    assert "Clear-OfficeCache -LocalAppData $OriginalLocalAppData" in installer


def test_desktop_shortcut_is_created_in_user_desktop_and_runs_ps1_panel():
    shortcut = (ROOT / "tools" / "create-desktop-shortcut.ps1").read_text(encoding="utf-8")
    assert "param(" in shortcut
    assert "DesktopPath" in shortcut
    assert "powershell.exe" in shortcut
    assert "-STA" in shortcut
    assert "CSM.ps1" in shortcut


def test_cmd_launcher_reports_missing_or_failed_panel():
    launcher_cmd = (ROOT / "tools" / "CSM.cmd").read_text(encoding="utf-8")
    assert "CSM.ps1" in launcher_cmd
    assert "Nie znaleziono panelu" in launcher_cmd
    assert "Panel zakonczyl sie bledem" in launcher_cmd
    assert "pause" in launcher_cmd


def test_installer_uses_localized_or_sid_based_share_accounts():
    installer = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    assert "Resolve-AccountName" in installer
    assert "S-1-1-0" in installer
    assert "S-1-5-32-545" in installer
    assert "Grant-AddinReadAccess" in installer
    assert "New-SmbShare nie powiodl sie" in installer
    assert "net share zwrocil kod" in installer
    assert "Ensure-LanmanServer" in installer
    assert "Invoke-NativeLogged" in installer
    assert "Test-AddinShare" in installer
    assert "Wait-AddinShare" in installer
    assert "Initialize-InstallLog" in installer


def test_elevated_phase_logs_real_admin_error_before_returning_code_1():
    installer = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    assert "BLAD etapu administratora" in installer
    assert "ScriptStackTrace" in installer
    assert "Ostatnie linie logu" in installer
    assert "Get-Content -Path $LogPath -Tail" in installer
    assert "exit 1" in installer


def test_share_problem_does_not_block_desktop_shortcut_and_user_phase():
    installer = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    assert "Instalacja bedzie kontynuowana, aby utworzyc skrot CSM" in installer
    assert "Etap administratora zakonczony z ostrzezeniem" in installer
    assert "Instalacja zakonczona z ostrzezeniem dotyczacym udzialu Worda" in installer
    assert "$script:ShareReady = $false" in installer
    assert "nie udalo sie uruchomic uslugi LanmanServer" in installer
    assert "Instalacja nie zostanie przerwana" in installer


def test_missing_old_share_does_not_break_admin_phase():
    installer = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
    assert "Test-MissingShareMessage" in installer
    assert "nie istnieje" in installer
    assert "Brak poprzedniego udzialu $ShareName do usuniecia" in installer
    assert "czyszczenie poprzedniego udzialu $ShareName nie powiodlo sie, ale instalacja nie zostanie przerwana" in installer
    assert "Start-Process -FilePath $FilePath -ArgumentList $Arguments" in installer
    assert "RedirectStandardError" in installer
    assert "harmless net.exe stderr" in installer
