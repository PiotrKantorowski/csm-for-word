from pathlib import Path
import py_compile

ROOT = Path(__file__).resolve().parents[1]
START = (ROOT / "tools" / "start-claude-safe-mode.ps1").read_text(encoding="utf-8")
INSTALL = (ROOT / "tools" / "install-csm.ps1").read_text(encoding="utf-8")
SERVER = ROOT / "server" / "static_addin_server.py"


def test_static_addin_server_script_exists_and_compiles() -> None:
    assert SERVER.exists()
    py_compile.compile(str(SERVER), doraise=True)
    text = SERVER.read_text(encoding="utf-8")
    assert "CSM add-in HTTPS server listening" in text
    assert "all-localhost" in text
    assert "IPv6LoopbackThreadingHttpServer" in text
    assert "Cache-Control" in text
    assert "Access-Control-Allow-Origin" in text
    assert "ssl.SSLContext" in text
    assert "taskpane.html" in text


def test_start_script_uses_python_static_server_not_npx_http_server_for_runtime() -> None:
    assert '$AddinStaticServer = Join-Path $ServerDir "static_addin_server.py"' in START
    assert "START Python addin HTTPS server" in START
    assert "--root '$AddinDir' --cert '$CertFile' --key '$KeyFile' --host 'all-localhost' --port 3000" in START
    addin_start = START[START.index("function Start-AddinServer"):]
    assert "npx http-server" not in addin_start
    assert "Test-AddinFilesReady" in addin_start
    assert "Write-LogTail -Path $AddinLog" in addin_start


def test_installer_waits_for_csm_start_result_instead_of_fire_and_forget() -> None:
    assert "Uruchamiam CSM i sprawdzam, czy localhost:3000 jest gotowy" in INSTALL
    assert "& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $start -NoOpenWord -NonInteractive" in INSTALL
    assert "if ($LASTEXITCODE -ne 0)" in INSTALL
    start_func = INSTALL[INSTALL.index("function Start-CSM"):INSTALL.index("function Enable-Autostart")]
    assert "Start-Process -FilePath \"powershell.exe\"" not in start_func
