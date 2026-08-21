from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")

def test_setup_ignores_pip_cache_warning_and_disables_cache():
    text = read("tools/setup-once.ps1")
    assert '--no-cache-dir' in text
    assert 'force-reinstall' in text
    assert 'import fastapi, uvicorn, pydantic, lxml.etree' in text
    # rc11 no longer relies on PowerShell error preference tricks; native pip
    # output is captured via Start-Process and failures are judged by exit code.
    assert 'Start-Process -FilePath $FilePath' in text
    assert 'RedirectStandardError' in text

def test_start_always_verifies_localhost_certificate_even_if_files_exist():
    text = read("tools/start-claude-safe-mode.ps1")
    assert 'Always run the certificate verifier' in text
    assert 'Word/WebView block the add-in content' in text
    assert '& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $certScript' in text

def test_cert_script_verifies_current_user_root_and_trusted_people():
    text = read("tools/ensure-localhost-cert.ps1")
    assert 'Test-CertificateTrustedStrict' in text
    assert 'TrustedPeople' in text
    assert 'CurrentUser\\Root' in text

def test_runtime_copy_no_longer_shows_v050_final2():
    combined = '\n'.join(read(rel) for rel in [
        'tools/install-csm.ps1',
        'addin/taskpane.html',
        'addin/manifest.xml',
    ])
    assert 'v0.5 — final6' not in combined
    assert 'v0.5.0 final2' not in combined
    assert '20260516-final6' not in combined
    # Accept rc17, rc18, or rc19+
    assert any(v in combined for v in ('v1.0 — rc17', 'v1.0 rc17', 'v1.0 — rc18', 'v1.0 rc18', 'v1.0 — rc19', 'v1.0 rc19', 'v1.0 — 0.6.1', 'v1.0 0.6.1'))
