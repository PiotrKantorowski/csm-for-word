from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_main_flow_prioritizes_negotiation_mode():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    assert "Sprawdź najnowszą wersję" in html
    assert "https://skills.kancelariakantorowski.pl/" in html
    assert "Bezpieczna kopia dokumentu" in html
    assert "Utwórz zanonimizowaną kopię" in html
    assert "Przywróć wersję jawną" in html
    assert "CSM sam tworzy kopię do pracy z AI" in html
    assert "Główne akcje" not in html


def test_emergency_restore_is_collapsed_below_main_flow():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    assert "Opcje awaryjne" in html
    assert "Awaryjnie przywróć wersję jawną z pliku" in html
    assert html.index("Bezpieczna kopia dokumentu") < html.index("Opcje awaryjne")


def test_step_panel_was_removed_in_favor_of_two_primary_buttons():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "Kroki pracy z dokumentem" not in html
    assert 'bindClickableStep("step2", v4PrepareDocxCopy)' not in js
    assert 'bindClickableStep("step4", v4RestoreDocxCopy)' not in js
