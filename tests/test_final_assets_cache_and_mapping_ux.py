from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_office_manifest_uses_cache_busted_csm_assets():
    manifest = (ROOT / "addin" / "manifest.xml").read_text(encoding="utf-8")
    assert "icon-16-csm-final6.png?build=20260710-1.6" in manifest
    assert "icon-32-csm-final6.png?build=20260710-1.6" in manifest
    assert "icon-80-csm-final6.png?build=20260710-1.6" in manifest
    assert "taskpane.html?build=20260710-1.6" in manifest
    assert "commands.html?build=20260710-1.6" in manifest


def test_taskpane_uses_single_versioned_logo_and_simple_version_label():
    taskpane = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    assert "assets/logo-csm-primary.png" in taskpane
    assert "logo-csm-monochrome-v050.png" not in taskpane
    assert 'class="brand-link"' in taskpane
    assert "v1.6" in taskpane
    assert "taskpane.js?v=1.6-20260710" in taskpane


def test_final_mapping_actions_are_prompt_based_not_self_merge():
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "promptForMergeTarget" in js
    assert "promptForManualCategory" in js
    assert "Nie dodano scalania placeholdera samego do siebie" in js
    assert "`${rawPlaceholder} => ${rawPlaceholder}`" not in js


def test_final6_does_not_reference_old_cache_busted_assets():
    manifest = (ROOT / "addin" / "manifest.xml").read_text(encoding="utf-8")
    taskpane = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    combined = manifest + "\n" + taskpane
    assert "20260516-r1" not in combined
    assert "v05r1.png?build" not in combined
    assert "0.6.1-r1-20260516" not in combined
    assert "0.6.1-final-20260516" not in combined
