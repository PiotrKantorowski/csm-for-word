from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
API = (ROOT / "server" / "api.py").read_text(encoding="utf-8")


def test_all_bound_buttons_exist_for_clean_startup_status():
    bound = re.findall(r'bindButton\("([^"]+)"', JS)
    missing = [button_id for button_id in bound if f'id="{button_id}"' not in HTML]
    assert missing == []


def test_busy_state_disables_v4_main_actions():
    assert '"btnV4Prepare", "btnV4Restore"' in JS
    assert 'progressCard.classList.remove("hidden")' in JS
    assert "showButtonLoading" in JS
    assert 'setBusy(true, "Tworzę i otwieram kopię do pracy z Claude...", "btnV4Prepare")' in JS
    assert 'setBusy(true, "Tworzę i otwieram wersję jawną...", "btnV4Restore")' in JS


def test_main_actions_have_responsive_tablet_layout():
    assert "negotiation-actions" in HTML
    assert "@media (min-width: 640px)" in HTML
    assert "grid-template-columns: 1fr 1fr" in HTML


def test_frontend_v4_current_endpoints_exist_in_backend():
    for endpoint in ["/v4/current/prepare", "/v4/current/restore"]:
        assert f'apiPostHeavy("{endpoint}"' in JS or f'apiPost("{endpoint}"' in JS
        assert f'@app.post("{endpoint}"' in API


def test_main_ux_does_not_expose_manual_file_controls():
    main_area = HTML.split('<div class="card negotiation-card"', 1)[1].split('<div class="support-card"', 1)[0]
    assert 'type="file"' not in main_area
    assert 'Pobierz plik' not in main_area
    assert 'Wybierz plik' not in main_area
    assert 'Utwórz zanonimizowaną kopię' in main_area
    assert 'Przywróć wersję jawną' in main_area
