from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mask_visible_range_retry_is_revision_aware():
    taskpane = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "maskVisibleTextByRange" in taskpane
    assert "preserveRevisionContext: true" in taskpane
    assert "Placeholdery były podmieniane w dwóch turach" in taskpane


def test_busy_progress_indicator_is_present():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    assert 'id="progressCard"' in html
    assert 'class="progress-spinner"' in html
    assert "Operacja w toku…" in html


def test_partner_logos_are_before_diagnostics_and_smaller():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    brand_idx = html.index('class="brand-panel"')
    diagnostics_idx = html.index("Kontrola działania")
    assert brand_idx < diagnostics_idx
    assert "brand-logo-csm" in html
    assert "max-height:42px" in html
    assert "Coś nie działa?" in html
    assert "https://kancelariakantorowski.pl/" in html
    assert "csm-top-logo" not in html
