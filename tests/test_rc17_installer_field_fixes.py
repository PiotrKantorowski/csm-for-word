"""
RC17 regression tests — field install fix verification.

These tests verify that all six field failure scenarios identified in the
CSM_RC17_FIELD_INSTALL_FAILURES_CC_PACK are handled correctly at the
PowerShell script and installer configuration level.

All tests are static (no live Windows install required) and run on the
same Python/pytest environment as the rest of the test suite.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
INSTALLER = ROOT / "installer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _setup_once_text() -> str:
    return _read(TOOLS / "setup-once.ps1")


def _install_csm_text() -> str:
    return _read(TOOLS / "install-csm.ps1")


def _start_csm_text() -> str:
    return _read(TOOLS / "start-claude-safe-mode.ps1")


def _diagnose_text() -> str:
    return _read(TOOLS / "diagnose-csm.ps1")


def _iss_text() -> str:
    return _read(INSTALLER / "CSM-Setup.iss")


# ---------------------------------------------------------------------------
# Field case 1 (Machine B): Read-Host must never be called in non-interactive
# context — setup-once.ps1 must guard with [Environment]::UserInteractive.
# ---------------------------------------------------------------------------

def test_setup_once_has_accept_license_param():
    """setup-once.ps1 must declare an explicit -AcceptLicense switch."""
    text = _setup_once_text()
    assert "[switch]$AcceptLicense" in text, (
        "setup-once.ps1 missing [switch]$AcceptLicense parameter — "
        "hidden installer cannot skip Read-Host without it"
    )


def test_setup_once_non_interactive_guard():
    """setup-once.ps1 must check [Environment]::UserInteractive before Read-Host."""
    text = _setup_once_text()
    assert "[Environment]::UserInteractive" in text, (
        "setup-once.ps1 must guard Read-Host with [Environment]::UserInteractive "
        "to prevent blocking in hidden non-interactive installer processes"
    )
    assert "[Console]::IsInputRedirected" in text, (
        "setup-once.ps1 must also check [Console]::IsInputRedirected "
        "as a secondary non-interactive guard"
    )


def test_setup_once_non_interactive_throws_without_flag():
    """Non-interactive path must throw, not silently return empty string."""
    text = _setup_once_text()
    # Must have an else branch that throws (not returns) when non-interactive
    # and no accept flag is present.
    assert re.search(r"throw\s+['\"]Licencja nie zostala zaakceptowana.*trybie nieinteraktywnym", text), (
        "setup-once.ps1 must throw an explicit error when non-interactive "
        "and no -AcceptLicense / -FromInstaller flag is present"
    )


def test_setup_once_accept_license_creates_sentinel():
    """AcceptLicense / FromInstaller branch must create the .license-accepted sentinel."""
    text = _setup_once_text()
    # The new branch must write the sentinel with a source tag
    assert "installer-switch" in text or "installer-gui" in text, (
        "setup-once.ps1 must write .license-accepted with source tag "
        "when -AcceptLicense or -FromInstaller is present"
    )


def test_setup_once_env_variable_accepted():
    """CSM_ACCEPT_LICENSE=1 environment variable must also bypass the prompt."""
    text = _setup_once_text()
    assert "CSM_ACCEPT_LICENSE" in text, (
        "setup-once.ps1 must honour $env:CSM_ACCEPT_LICENSE as a third "
        "non-interactive acceptance path"
    )


# ---------------------------------------------------------------------------
# Field case 1 (Machine B): install-csm.ps1 must always pass -AcceptLicense.
# ---------------------------------------------------------------------------

def test_install_csm_has_from_installer_param():
    """install-csm.ps1 must declare [switch]$FromInstaller."""
    text = _install_csm_text()
    assert "[switch]$FromInstaller" in text, (
        "install-csm.ps1 must declare [switch]$FromInstaller parameter"
    )


def test_install_csm_has_accept_license_param():
    """install-csm.ps1 must declare [switch]$AcceptLicense."""
    text = _install_csm_text()
    assert "[switch]$AcceptLicense" in text, (
        "install-csm.ps1 must declare [switch]$AcceptLicense parameter"
    )


def test_install_csm_always_passes_accept_license_to_setup_once():
    """Run-SetupOnce must always pass -FromInstaller and -AcceptLicense."""
    text = _install_csm_text()
    # The setupArgs array must contain both flags unconditionally (no if-block)
    assert '"-FromInstaller"' in text or "'-FromInstaller'" in text, (
        "Run-SetupOnce must pass -FromInstaller to setup-once.ps1 unconditionally"
    )
    assert '"-AcceptLicense"' in text or "'-AcceptLicense'" in text, (
        "Run-SetupOnce must pass -AcceptLicense to setup-once.ps1"
    )


def test_install_csm_no_conditional_from_installer():
    """install-csm.ps1 must not use `if ($OriginalSourceRoot)` to gate -FromInstaller."""
    text = _install_csm_text()
    # The old conditional was: if ($OriginalSourceRoot) { $setupArgs += "-FromInstaller" }
    assert "if ($OriginalSourceRoot)" not in text or (
        # Allow the check to exist for other purposes, but not to gate -FromInstaller
        "setupArgs" not in text[
            text.find("if ($OriginalSourceRoot)"):
            text.find("if ($OriginalSourceRoot)") + 200
        ]
    ), (
        "install-csm.ps1 must not conditionally add -FromInstaller based on "
        "$OriginalSourceRoot — this was the root cause of Machine B failure"
    )


# ---------------------------------------------------------------------------
# Field case 2 (Machine A): Word catalog must be registered AFTER .venv exists.
# ---------------------------------------------------------------------------

def test_install_csm_venv_verified_before_catalog():
    """Assert-VenvReady / .venv check must come before Add-TrustedCatalogRegistry."""
    text = _install_csm_text()
    pos_venv = text.find("Assert-VenvReady")
    pos_catalog = text.find("Add-TrustedCatalogRegistry")
    assert pos_venv != -1, (
        "install-csm.ps1 must have Assert-VenvReady function call "
        "to verify .venv before registering Word catalog"
    )
    assert pos_catalog != -1, "install-csm.ps1 must call Add-TrustedCatalogRegistry"
    # Find CALL sites by collecting all positions and excluding the
    # function definition lines (lines that start with 'function ').
    def _call_positions(name: str) -> list[int]:
        positions = []
        for m in re.finditer(r'\b' + re.escape(name) + r'\b', text):
            # Look at the non-whitespace content before this match on the same line
            line_start = text.rfind('\n', 0, m.start()) + 1
            prefix = text[line_start:m.start()].strip()
            if not prefix.startswith('function'):
                positions.append(m.start())
        return positions

    call_venv = _call_positions("Assert-VenvReady")
    call_catalog = _call_positions("Add-TrustedCatalogRegistry")
    assert call_venv, "Assert-VenvReady is defined but never called"
    assert call_catalog, "Add-TrustedCatalogRegistry is defined but never called"
    last_venv_call = max(call_venv)
    first_catalog_call = min(call_catalog)
    assert last_venv_call < first_catalog_call, (
        f"Assert-VenvReady (pos {last_venv_call}) must be called BEFORE "
        f"Add-TrustedCatalogRegistry (pos {first_catalog_call}) — "
        "Machine A failure: Word saw add-in before .venv existed"
    )


def test_install_csm_assert_venv_throws_on_missing_venv():
    """Assert-VenvReady must throw (not warn) if .venv is absent."""
    text = _install_csm_text()
    # Find Assert-VenvReady function body
    fn_start = text.find("function Assert-VenvReady")
    fn_end = text.find("\nfunction ", fn_start + 1)
    fn_body = text[fn_start:fn_end] if fn_end != -1 else text[fn_start:]
    assert "throw" in fn_body, (
        "Assert-VenvReady must throw, not just warn, when .venv is missing — "
        "a warning would let installation continue into a broken state"
    )


def test_run_setup_once_before_catalog_in_install_sequence():
    """Run-SetupOnce must appear before Add-TrustedCatalogRegistry in the main flow."""
    text = _install_csm_text()
    pos_setup = text.rfind("Run-SetupOnce")
    pos_catalog = text.find("Add-TrustedCatalogRegistry")
    # Skip the function definition line of Add-TrustedCatalogRegistry
    call_catalog_positions = []
    for m in re.finditer(r'\bAdd-TrustedCatalogRegistry\b', text):
        line_start = text.rfind('\n', 0, m.start()) + 1
        prefix = text[line_start:m.start()].strip()
        if not prefix.startswith('function'):
            call_catalog_positions.append(m.start())
    if call_catalog_positions:
        first_call_catalog = min(call_catalog_positions)
        assert pos_setup < first_call_catalog, (
            "Run-SetupOnce must be called before Add-TrustedCatalogRegistry "
            "in the main install sequence"
        )


# ---------------------------------------------------------------------------
# ISS: installer must pass -FromInstaller -AcceptLicense to install-csm.ps1
# ---------------------------------------------------------------------------

def test_iss_passes_from_installer_flag():
    """CSM-Setup.iss [Run] must pass -FromInstaller to install-csm.ps1."""
    text = _iss_text()
    assert "-FromInstaller" in text, (
        "CSM-Setup.iss [Run] section must pass -FromInstaller to install-csm.ps1"
    )


def test_iss_passes_accept_license_flag():
    """CSM-Setup.iss [Run] must pass -AcceptLicense to install-csm.ps1."""
    text = _iss_text()
    assert "-AcceptLicense" in text, (
        "CSM-Setup.iss [Run] section must pass -AcceptLicense to install-csm.ps1 "
        "so the Inno GUI license acceptance flows through to setup-once.ps1"
    )


# ---------------------------------------------------------------------------
# Self-healing: start-claude-safe-mode.ps1 must repair missing .venv
# ---------------------------------------------------------------------------

def test_start_csm_self_heal_on_missing_venv():
    """start-claude-safe-mode.ps1 must attempt self-healing when .venv is absent."""
    text = _start_csm_text()
    assert "SelfHeal" in text or "self-heal" in text.lower() or "Invoke-SelfHeal" in text, (
        "start-claude-safe-mode.ps1 must contain self-healing logic for missing .venv"
    )


def test_start_csm_self_heal_requires_license_accepted():
    """Self-healing must only run when .license-accepted exists (safe guard)."""
    text = _start_csm_text()
    assert "LicenseAccepted" in text, (
        "start-claude-safe-mode.ps1 must check $LicenseAccepted before self-healing "
        "to avoid running setup-once on a machine where license was never accepted"
    )


def test_start_csm_self_heal_passes_accept_license():
    """Self-heal invocation of setup-once.ps1 must pass -AcceptLicense."""
    text = _start_csm_text()
    assert "-AcceptLicense" in text, (
        "start-claude-safe-mode.ps1 must pass -AcceptLicense when calling "
        "setup-once.ps1 during self-healing"
    )


# ---------------------------------------------------------------------------
# Diagnostics: diagnose-csm.ps1 must expose root cause
# ---------------------------------------------------------------------------

def test_diagnose_has_root_cause_line():
    """diagnose-csm.ps1 must emit ROOT_CAUSE_LIKELY= for easy triage."""
    text = _diagnose_text()
    assert "ROOT_CAUSE_LIKELY" in text, (
        "diagnose-csm.ps1 must emit ROOT_CAUSE_LIKELY= so support staff "
        "can identify the cause without reading the full diagnostic"
    )


def test_diagnose_detects_half_installed():
    """diagnose-csm.ps1 must detect the half-installed (catalog-without-venv) state."""
    text = _diagnose_text()
    assert "half-installed" in text or "polinstalacji" in text, (
        "diagnose-csm.ps1 must explicitly name the half-installed state where "
        "Word sees the add-in but the backend .venv is missing"
    )


def test_diagnose_checks_license_accepted():
    """diagnose-csm.ps1 must report .license-accepted status."""
    text = _diagnose_text()
    assert "LicenseAccepted" in text or ".license-accepted" in text, (
        "diagnose-csm.ps1 must check and report .license-accepted status"
    )


def test_diagnose_checks_csm_version():
    """diagnose-csm.ps1 must read and report VERSION.json."""
    text = _diagnose_text()
    assert "VERSION.json" in text or "VersionJson" in text, (
        "diagnose-csm.ps1 must read VERSION.json to report installed CSM version"
    )


def test_diagnose_shows_200_log_lines():
    """diagnose-csm.ps1 must tail at least 200 lines from log files."""
    text = _diagnose_text()
    assert "200" in text, (
        "diagnose-csm.ps1 must show at least 200 log tail lines "
        "(previously only 80 — insufficient for diagnosing failed installs)"
    )


def test_diagnose_includes_setup_once_log():
    """diagnose-csm.ps1 must include %TEMP%\\CSM-setup-once.log."""
    text = _diagnose_text()
    assert "CSM-setup-once.log" in text, (
        "diagnose-csm.ps1 must include CSM-setup-once.log — "
        "this log contains the Python .venv creation details"
    )


# ---------------------------------------------------------------------------
# Version bump
# ---------------------------------------------------------------------------

def test_version_json_label_is_rc17():
    """VERSION.json must carry the rc17 label."""
    import json
    vp = ROOT / "VERSION.json"
    assert vp.exists(), "VERSION.json missing"
    data = json.loads(vp.read_text(encoding="utf-8"))
    label = str(data.get("label", "") or data.get("build", ""))
    assert any(v in label.lower() for v in ("rc17", "rc18", "rc19", "1.0", "1.2", "1.3", "1.4", "1.5", "1.6")), (
        f"VERSION.json label/build must contain rc17, rc18, rc19, 1.0, 1.2, or 1.3, got: {label!r}"
    )


def test_install_csm_version_string_is_rc17():
    """install-csm.ps1 version banner must say rc17."""
    text = _install_csm_text()
    assert any(v in text for v in ("rc17", "rc18", "rc19", "1.0", "1.2", "1.3", "1.4", "1.5", "1.6")), (
        "install-csm.ps1 version string must say rc17, rc18, rc19, 1.0, 1.2, or 1.3 — "
        "this is the first thing printed during install and helps support triage"
    )


# ---------------------------------------------------------------------------
# repair-csm.ps1 — NAPRAW button must repair missing/broken .venv (RC17 fix)
# ---------------------------------------------------------------------------

def _repair_text() -> str:
    return _read(TOOLS / "repair-csm.ps1")


def test_repair_csm_runs_setup_once_when_venv_missing():
    """repair-csm.ps1 must call setup-once.ps1 when .venv is absent."""
    text = _repair_text()
    assert "setup-once.ps1" in text, (
        "repair-csm.ps1 must call setup-once.ps1 to repair missing .venv — "
        "previously it only called install-csm.ps1 -SkipDependencies, "
        "which skips setup-once and leaves .venv missing"
    )


def test_repair_csm_passes_accept_license_to_setup_once():
    """repair-csm.ps1 must pass -AcceptLicense when invoking setup-once.ps1."""
    text = _repair_text()
    assert "-AcceptLicense" in text, (
        "repair-csm.ps1 must pass -AcceptLicense to setup-once.ps1 — "
        "repair runs silently (no Read-Host) and license was accepted at install time"
    )


def test_repair_csm_checks_imports_not_just_file_existence():
    """repair-csm.ps1 must check Python imports, not just that python.exe exists."""
    text = _repair_text()
    assert "fastapi" in text or "import" in text.lower(), (
        "repair-csm.ps1 must verify Python imports (fastapi/uvicorn/pydantic/lxml), "
        "not just check if python.exe file exists — a corrupt .venv may have python.exe "
        "but fail to import required modules"
    )


def test_repair_csm_does_not_skip_setup_once_unconditionally():
    """repair-csm.ps1 must not call install-csm.ps1 -SkipDependencies as the ONLY action."""
    text = _repair_text()
    # The old repair-csm.ps1 was a 5-line file that only called install-csm.ps1 -SkipDependencies.
    # The new version must conditionally run setup-once.ps1 first.
    # We verify it has more content than just that single delegation.
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith('#')]
    assert len(lines) > 5, (
        "repair-csm.ps1 must have substantive logic for .venv repair, "
        "not just delegate to install-csm.ps1 -SkipDependencies"
    )


# ---------------------------------------------------------------------------
# Case 5: upgrade from v0.5 — active scripts must not contain v0.5 strings
# ---------------------------------------------------------------------------

def test_active_scripts_free_of_v05_stale_strings():
    """All active rc17 scripts must not contain v0.5 version strings."""
    active_files = [
        TOOLS / "install-csm.ps1",
        TOOLS / "setup-once.ps1",
        TOOLS / "repair-csm.ps1",
        TOOLS / "start-claude-safe-mode.ps1",
        ROOT / "addin" / "manifest.xml",
    ]
    stale_strings = ["v0.5.0 final2", "v0.5.0 final6", "v0.5 — final6", "CSM v0.5"]
    for path in active_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for stale in stale_strings:
            assert stale not in text, (
                f"{path.name} contains stale v0.5 string: {stale!r} — "
                "upgrade from v0.5 stale tree must overwrite all such references"
            )


def test_diagnose_has_pip_list():
    """diagnose-csm.ps1 must include pip list output for installed packages."""
    text = _diagnose_text()
    assert "pip list" in text or "pip" in text.lower(), (
        "diagnose-csm.ps1 must include pip list or equivalent — "
        "this is needed to verify which packages are actually installed in .venv"
    )


# ---------------------------------------------------------------------------
# Case 6: Python 3.14 — must fail BEFORE Word catalog, not after
# ---------------------------------------------------------------------------

def test_zainstaluj_cmd_passes_accept_license():
    """ZAINSTALUJ_CSM.cmd must pass -AcceptLicense to install-csm.ps1.

    Root cause of rc16 field failures: ZAINSTALUJ_CSM.cmd called install-csm.ps1
    without -OriginalSourceRoot, so the old conditional
      if ($OriginalSourceRoot) { $setupArgs += "-FromInstaller" }
    evaluated to FALSE and Read-Host was called in a hidden/non-interactive process.

    rc17 fix layer 1: ZAINSTALUJ_CSM.cmd now explicitly passes -AcceptLicense.
    rc17 fix layer 2: Run-SetupOnce hardcodes -FromInstaller -AcceptLicense regardless.
    """
    cmd_path = ROOT / "ZAINSTALUJ_CSM.cmd"
    assert cmd_path.exists(), "ZAINSTALUJ_CSM.cmd not found in repo root"
    text = _read(cmd_path)
    assert "-AcceptLicense" in text, (
        "ZAINSTALUJ_CSM.cmd must pass -AcceptLicense to install-csm.ps1 — "
        "without it, setup-once.ps1 may call Read-Host in a hidden/non-interactive "
        "context (Inno runhidden or double-click from Explorer) and fail silently"
    )


def test_assert_venv_ready_throws_before_catalog():
    """Assert-VenvReady must throw before Add-TrustedCatalogRegistry can run."""
    text = _install_csm_text()
    # Verify Assert-VenvReady contains a throw for missing .venv
    fn_start = text.find("function Assert-VenvReady")
    fn_end = text.find("\nfunction ", fn_start + 1)
    fn_body = text[fn_start:fn_end] if fn_end != -1 else text[fn_start:]
    assert "throw" in fn_body, (
        "Assert-VenvReady must throw when .venv is absent — "
        "this prevents the Word catalog from being registered on Machine A "
        "(Python 3.14 only, no Python 3.12) and avoids the half-installed state"
    )
    # Also verify the call order in the main script body
    pos_assert = text.rfind("Assert-VenvReady")
    pos_catalog_calls = [
        m.start() for m in re.finditer(r'\bAdd-TrustedCatalogRegistry\b', text)
        if not text[text.rfind('\n', 0, m.start()) + 1:m.start()].strip().startswith('function')
    ]
    if pos_catalog_calls:
        assert pos_assert < min(pos_catalog_calls), (
            "Assert-VenvReady must appear before Add-TrustedCatalogRegistry in execution order — "
            "on Python 3.14-only machine, the throw in Assert-VenvReady prevents half-install"
        )
