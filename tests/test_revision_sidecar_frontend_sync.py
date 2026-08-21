from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
HTML = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
API = (ROOT / "server" / "api.py").read_text(encoding="utf-8")


def test_frontend_has_authenticated_api_get_with_token_refresh():
    assert "async function apiGet" in JS
    assert "async function getJson" in JS
    assert 'method: "GET"' in JS
    assert "headers: apiHeaders()" in JS
    assert "res.status === 401" in JS
    assert "apiGet ${path}: HTTP 401" in JS
    assert "loadRuntimeTokenFresh({ backendFirst: true })" in JS


def test_frontend_can_check_secured_sidecar_status_endpoint():
    assert 'apiGet("/v2/revision/sidecar/status")' in JS
    assert "function formatRevisionSidecarStatus" in JS
    assert "async function checkRevisionSidecarStatus" in JS
    assert 'id="btnRevisionSidecarStatus"' in HTML
    assert 'bindButton("btnRevisionSidecarStatus", () => checkRevisionSidecarStatus({ show: true }))' in JS
    assert '@app.get("/v2/revision/sidecar/status"' in API


def test_technical_status_includes_redacted_sidecar_diagnostics_without_command_values():
    status_fn = JS[JS.index("async function showTechnicalStatus") : JS.index("// ─── Auto-restore guards")]
    assert "checkRevisionSidecarStatus({ show: false })" in status_fn
    assert "formatRevisionSidecarStatus(sidecar)" in status_fn
    assert "Moduł revision_bridge.js" in status_fn
    assert "lastRevisionSidecarStatus" in JS
    assert "Program pomocniczy wskazany w konfiguracji" in JS
    assert "Program pomocniczy odnaleziony" in JS
    assert "Sprawdzenie uruchomienia" in JS
    assert "Moduł odpowiada" in JS
    assert "Obsługiwane funkcje" in JS


def test_revision_status_wording_is_lawyer_friendly():
    user_visible = JS + "\n" + HTML
    assert "Sprawdź śledzenie zmian" in HTML
    assert "Mechanizm zachowania śledzenia zmian" in JS
    assert "sidecar rewizji OOXML" not in user_visible.lower()
    assert "Capabilities" not in user_visible
    assert "Sonda statusu" not in user_visible
    assert "Wykonywalny odnaleziony" not in user_visible
