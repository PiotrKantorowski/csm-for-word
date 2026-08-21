from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")


def test_latest_version_link_replaces_csm_logo():
    assert "Sprawdź najnowszą wersję" in HTML
    assert "https://skills.kancelariakantorowski.pl/" in HTML
    assert "csm-top-logo" not in HTML
    assert "csm-top-mark" not in HTML


def test_csm_logos_are_before_diagnostics_and_sized():
    brand_idx = HTML.index('aria-label="CSM"')
    diagnostics_idx = HTML.index("Kontrola działania")
    assert brand_idx < diagnostics_idx
    assert "brand-logo-csm" in HTML
    assert "max-height:42px" in HTML


def test_no_old_logo_caption():
    assert "Kliknij logo, aby przejść" not in HTML
