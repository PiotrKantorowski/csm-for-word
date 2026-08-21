from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_csm_vps_env_enables_remote_bielik_contract():
    provision = read("tools/provision-vps.ps1")
    assert "CSM_PUBLIC_API_URL=https://${Domain}" in provision
    assert "CSMW_ENABLE_BIELIK=1" in provision
    assert "CSMW_BIELIK_PROVIDER=ollama" in provision
    assert "CSMW_BIELIK_MODEL=${Model}" in provision
    assert "CSMW_BIELIK_URL=http://127.0.0.1:11434/api/chat" in provision


def test_csm_addin_can_use_generated_vps_api_base():
    taskpane = read("addin/taskpane.js")
    assert "window.CSM_API_BASE" in taskpane
    assert "window.CSM_API_BASE_CANDIDATES" in taskpane
    assert "DEFAULT_LOCAL_API_BASE" in taskpane


def test_csm_health_exposes_vps_panel_metadata():
    api = read("server/api.py")
    assert "CSM_ALLOWED_ORIGINS" in api
    assert '"remote_mode"' in api
    assert '"api_base_url"' in api
    assert '"embedding_provider"' in api
    assert '"bielik_model"' in api


def test_csm_installer_normalizes_region_code_before_provisioning():
    installer = read("installer/CSM-Setup.iss")
    assert "function NormalizeRegion" in installer
    assert "Region := NormalizeRegion(GVpsRegionCombo.Text);" in installer
    assert "GVpsRegionCombo.Items.Clear" in installer


def test_csm_vps_helper_scripts_are_shipped():
    write_config = ROOT / "tools" / "write-vps-config.ps1"
    manifest = ROOT / "tools" / "build-vps-manifest.ps1"
    assert write_config.exists()
    assert manifest.exists()
    assert "window.CSM_API_BASE" in write_config.read_text(encoding="utf-8")
    manifest_text = manifest.read_text(encoding="utf-8")
    assert "manifest-vps.xml" in manifest_text
    assert '$updated = $value -replace "^https://localhost:3000", $addinOrigin' in manifest_text
    assert '$node.SetAttribute("DefaultValue", $updated)' in manifest_text
    assert 'RemoveChild($domain)' in manifest_text
