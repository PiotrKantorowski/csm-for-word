from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_profile_selector_is_visible_next_to_main_docx_action_and_single_id():
    html = read("addin/taskpane.html")
    assert html.count('id="documentProfile"') == 1
    assert '<div class="profile-selector"' in html
    assert html.index('id="documentProfile"') < html.index('id="btnV4Prepare"')
    assert "Pisma procesowe" in html
    assert "Umowy" in html
    assert "Wybór zostanie zapisany w dokumencie CSM" in html


def test_profile_is_saved_to_document_settings_and_restored_from_metadata():
    js = read("addin/taskpane.js")
    assert 'const DOCUMENT_PROFILE_SETTING_KEY = "CSM_DOCUMENT_PROFILE"' in js
    assert "async function persistSelectedDocumentProfile" in js
    assert "metadata.document_profile" in js
    assert 'await persistSelectedDocumentProfile(metadata.document_profile, "metadata")' in js
    assert "const chosenProfile = await persistSelectedDocumentProfile" in js


def test_manual_rules_are_in_technical_settings_not_hidden_under_summary_only():
    html = read("addin/taskpane.html")
    assert "Własne reguły ukrywania danych" in html
    assert "Kroki pracy z dokumentem" not in html
    assert html.index("Własne reguły ukrywania danych") < html.index('id="manualAlways"')
    assert 'id="manualAlways"' in html
    assert 'id="manualNever"' in html


def test_desktop_and_installer_shortcuts_use_csm_ico():
    assert (ROOT / "assets" / "csm.ico").exists()
    assert (ROOT / "addin" / "assets" / "csm.ico").exists()
    shortcut = read("tools/create-desktop-shortcut.ps1")
    assert "$Shortcut.IconLocation = $IconPath" in shortcut
    installer = read("installer/CSM-Setup.iss")
    assert "UninstallDisplayIcon={app}\\assets\\csm.ico" in installer
    assert 'IconFilename: "{app}\\assets\\csm.ico"' in installer
    panel = read("tools/CSM.ps1")
    assert "$form.Icon = New-Object System.Drawing.Icon($IconPath)" in panel
