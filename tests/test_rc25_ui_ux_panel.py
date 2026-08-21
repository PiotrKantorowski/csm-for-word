from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")


def test_manual_rule_placeholder_uses_generic_jan_kowalski_example():
    assert "np. Jan Kowalski" in HTML
    assert "Bernardeta Worosz" not in HTML
    assert "Bernardeta Wrzos" not in HTML


def test_manual_rules_panel_stays_visible_and_standalone():
    assert 'id="manualRulesPanel"' in HTML
    assert '<summary>Własne reguły ukrywania danych</summary>' in HTML
    assert 'id="manualRulesPanel" class="card soft technical-rules" open' in HTML
    control_pos = HTML.index('Kontrola działania')
    manual_pos = HTML.index('id="manualRulesPanel"')
    service_pos = HTML.index('id="servicePanel"')
    assert control_pos < manual_pos < service_pos


def test_steps_panel_is_removed_from_visible_ui_without_breaking_main_buttons():
    assert "Kroki pracy z dokumentem" not in HTML
    assert 'id="btnV4Prepare"' in HTML
    assert 'id="btnV4Restore"' in HTML
    assert 'bindButton("btnV4Prepare", v4PrepareDocxCopy)' in JS
    assert 'bindButton("btnV4Restore", v4RestoreDocxCopy)' in JS
    assert 'bindClickableStep("step2", v4PrepareDocxCopy)' not in JS
    assert 'bindClickableStep("step4", v4RestoreDocxCopy)' not in JS


def test_simplified_panels_use_layperson_labels():
    assert "Kontrola działania" in HTML
    assert "Własne reguły ukrywania danych" in HTML
    assert "Opcje awaryjne" in HTML
    assert "Serwis i instalacja CSM" in HTML
    assert "Pomoc i ustawienia zaawansowane" not in HTML
    assert "Zaawansowane / diagnostyka" not in HTML
    assert "Ustawienia techniczne: mapowania i reguły lokalne" not in HTML


def test_manual_rule_labels_are_plain_polish():
    assert "Zawsze ukrywaj te dane" in HTML
    assert "Nie ukrywaj tych danych" in HTML
    assert "Połącz błędnie rozdzielone oznaczenia" in HTML
    assert "Zmień typ ukrytej danej" not in HTML
    assert "Zawsze anonimizuj / zawsze wykluczaj jawność" not in HTML
    assert "Nigdy nie anonimizuj / nigdy nie wykluczaj z jawności" not in HTML


def test_service_panel_buttons_are_readable_and_not_silent():
    assert "Uruchom CSM" in HTML
    assert "Zatrzymaj CSM" in HTML
    assert "Napraw instalację" in HTML
    assert "Wyczyść cache Worda" in HTML
    assert "Pokaż logi instalacji" in HTML
    assert "tych opcji używaj tylko przy problemach technicznych" in HTML.lower()
    assert "async function apiPostService" in JS
    assert "return null;" in JS
    assert "Nie mam połączenia z lokalnym silnikiem CSM" in JS
    assert "BŁĄD panelu" not in JS
