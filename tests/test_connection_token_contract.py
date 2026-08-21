from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
START = (ROOT / "tools" / "start-claude-safe-mode.ps1").read_text(encoding="utf-8")
API = (ROOT / "server" / "api.py").read_text(encoding="utf-8")


def test_frontend_resynchronizes_token_from_backend_after_word_cache() -> None:
    assert "async function loadRuntimeTokenFromBackend()" in JS
    assert "fetchFromAnyApiBase(`/auth/bootstrap?ts=${Date.now()}`" in JS
    assert "API_BASE_CANDIDATES" in JS
    assert "http://localhost:8787" in JS
    assert "backendFirst" in JS
    assert "res.status === 401" in JS
    assert "odświeżam token z backendu i ponawiam żądanie" in JS
    api_post = JS[JS.index("async function apiPost"):JS.index("async function getLatestBackupMapId")]
    assert api_post.index("if (res.status === 401)") < api_post.index("if (!res.ok)")


def test_backend_exposes_local_bootstrap_token_endpoint() -> None:
    assert 'from security import token_matches, get_api_token' in API
    assert '@app.get("/auth/bootstrap")' in API
    assert '"token": token' in API
    assert '"token_required": True' in API


def test_wait_http_ready_accepts_only_2xx_not_4xx() -> None:
    """Wait-HttpReady must use a 2xx-only check, not 2xx-4xx.

    Regression for: the function accepted HTTP 4xx (including 404) as a
    readiness indicator. If http-server started but csm-token.js was missing,
    a 404 was treated as success and START declared the add-in server ready
    while the token file was absent.
    """
    # The condition must be -lt 300 (2xx only), not -lt 500 (also 4xx).
    assert "-lt 300" in START
    # Confirm the old permissive boundary is gone.
    import re
    assert not re.search(r"-lt\s+500", START), (
        "Wait-HttpReady still accepts 4xx as ready (found '-lt 500')"
    )


def test_start_script_waits_for_backend_and_auth_before_telling_user_to_open_word() -> None:
    assert "function Wait-HttpReady" in START
    assert "function Test-LocalAuth" in START
    assert 'Wait-HttpReady -Url "http://127.0.0.1:8787/health"' in START
    assert 'Invoke-WebRequest -Uri "http://127.0.0.1:8787/auth_check"' in START
    assert 'Token API zweryfikowany z backendem.' in START
    assert '$backendReady = Start-Backend' in START
    assert '$addinReady = Start-AddinServer' in START
    assert 'if ($backendReady -and $addinReady)' in START
    assert 'CSM jest uruchomiony i gotowy do pracy.' in START
    assert 'CSM NIE jest jeszcze gotowy do pracy.' in START
    assert 'exit 1' in START
    assert START.index('Wait-HttpReady -Url "http://127.0.0.1:8787/health"') < START.index('Write-Host "CSM jest uruchomiony i gotowy do pracy."')


def test_auth_bootstrap_returns_current_env_token() -> None:
    old_token = os.environ.get("CSM_API_TOKEN")
    os.environ["CSM_API_TOKEN"] = "test-token"
    sys.path.insert(0, str(ROOT / "server"))
    from fastapi.testclient import TestClient  # noqa: E402
    from api import app  # noqa: E402

    client = TestClient(app)
    r = client.get("/auth/bootstrap", headers={"Origin": "https://localhost:3000"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["token"] == "test-token"

    unauth = client.post("/auth_check", json={})
    assert unauth.status_code == 401

    authed = client.post("/auth_check", headers={"X-CSM-Token": data["token"]}, json={})
    assert authed.status_code == 200
    if old_token is None:
        os.environ.pop("CSM_API_TOKEN", None)
    else:
        os.environ["CSM_API_TOKEN"] = old_token


def test_start_script_runs_services_hidden_with_logs_and_pid_files() -> None:
    """Regression: service windows could be closed or appear hung.

    START should launch backend/add-in server as hidden background processes,
    record wrapper PIDs, and write logs that can be inspected when Word cannot
    reach localhost.
    """
    assert '$BackendLog = Join-Path $LogsDir "backend-8787.log"' in START
    assert '$AddinLog = Join-Path $LogsDir "addin-3000.log"' in START
    assert '$BackendPidFile = Join-Path $RuntimeDir "backend-wrapper.pid"' in START
    assert '$AddinPidFile = Join-Path $RuntimeDir "addin-wrapper.pid"' in START
    assert '-WindowStyle Hidden -PassThru' in START
    assert 'Write-ProcessId -Path $BackendPidFile' in START
    assert 'Write-ProcessId -Path $AddinPidFile' in START
    assert '-NoExit' not in START, "START should not leave user-closeable service PowerShell windows open"


def test_start_script_does_not_fail_addin_readiness_only_because_of_ps_tls_check() -> None:
    """PowerShell 5.1 may fail self-signed localhost TLS while Word works.

    Keep the strict 2xx HTTP readiness check, but add a conservative fallback:
    port 3000 listening + csm-token.js exists on disk. This prevents START from
    hanging/aborting on a console-only certificate verification artifact.
    """
    assert 'function Wait-TcpReady' in START
    assert '-IgnoreCertificateErrors' in START
    assert 'Wait-TcpReady -Port 3000' in START
    assert 'Test-Path -LiteralPath $AddinTokenFile' in START
