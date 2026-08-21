import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from redactor import make_replacements  # noqa: E402


def test_selftest_script_is_current_and_standalone():
    env = os.environ.copy()
    runtime = Path(tempfile.mkdtemp(prefix="csm-selftest-pytest-"))
    env["CSM_API_TOKEN"] = "test-token"
    env["CSM_BASE_DIR"] = str(runtime / "base")
    env["CSM_INSTALL_ROOT"] = str(runtime / "install")
    env["CSM_INSTALL_BACKUPS_DIR"] = str(runtime / "install" / "backups")
    env["CSM_DISABLE_OPEN_FILE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "tests/selftest.py"],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK: v1.0" in result.stdout


def test_generic_contract_heading_does_not_create_hidden_mapping():
    text = "UMOWA NAJMU LOKALU MIESZKALNEGO\nPrzedmiotem Umowy są Ogólne Warunki."
    masked, replacements = make_replacements(text)
    assert masked == text
    assert replacements == []
