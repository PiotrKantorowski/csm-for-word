from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_word_bridge_uses_two_pass_clean_then_tracked_replacements():
    bridge = (ROOT / "addin" / "word-bridge.js").read_text(encoding="utf-8")
    assert "classifyRangesForPair" in bridge
    assert "replaceClassifiedRanges(classified.clean" in bridge
    assert "replaceClassifiedRanges(classified.tracked" in bridge
    assert "replacedClean" in bridge
    assert "replacedTracked" in bridge
    assert "twoPass: true" in bridge
    assert "range.paragraphs.getFirst().getOoxml()" in bridge


def test_package_no_legacy_release_or_tester_notes():
    legacy = []
    for path in ROOT.iterdir():
        name = path.name
        if name.startswith("TESTER-NOTES-"):
            legacy.append(name)
        if name.startswith("RELEASE-NOTES-") and name != f"RELEASE-NOTES-v{__import__('json').loads((ROOT / 'VERSION.json').read_text(encoding='utf-8'))['version']}.txt":
            legacy.append(name)
    assert legacy == []


def test_ui_simplified_header_and_no_legacy_main_actions_text():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    assert "Sprawdź najnowszą wersję" in html
    assert "https://skills.kancelariakantorowski.pl/" in html
    assert "csm-top-logo" not in html
    assert "Kliknij logo, aby przejść" not in html
    assert "Główne akcje" not in html
    assert "brand-logo-csm" in html
    assert "max-height:42px" in html
