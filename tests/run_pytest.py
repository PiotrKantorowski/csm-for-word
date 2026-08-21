"""Stable project test runner.

CSM tests do not rely on external pytest plugins. Some developer machines and CI
images preload third-party pytest plugins, and FastAPI/TestClient cleanup can
leave background resources alive after pytest reports success. This runner runs
pytest once in a fresh Python subprocess, disables plugin autoload, disables
pytest's cache provider, uses isolated runtime folders, prevents OS file-open
side effects, and exits the child with os._exit().
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
PYTEST_TIMEOUT_SECONDS = 240


def cleanup_project_caches() -> None:
    for target in (ROOT / ".pytest_cache", ROOT / "server" / "__pycache__", ROOT / "tests" / "__pycache__"):
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        except OSError:
            pass


def prepare_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    test_runtime = Path(tempfile.mkdtemp(prefix="csm-pytest-"))
    # Force isolated paths for the test process; inherited developer env vars
    # must not redirect tests into the real project/install tree.
    env["CSM_BASE_DIR"] = str(test_runtime / "base")
    env["CSM_INSTALL_ROOT"] = str(test_runtime / "install")
    env["CSM_INSTALL_BACKUPS_DIR"] = str(test_runtime / "install" / "backups")
    env["CSM_DISABLE_OPEN_FILE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    server_path = str(ROOT / "server")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = server_path if not existing_pythonpath else server_path + os.pathsep + existing_pythonpath
    return env


def default_pytest_args(args: list[str]) -> list[str]:
    pytest_args = args if args else [str(TESTS)]
    if not any(a in ("-q", "--quiet") for a in pytest_args):
        pytest_args = ["-q", *pytest_args]
    return pytest_args


def run_pytest(args: list[str], env: dict[str, str]) -> int:
    # Run pytest inside a tiny wrapper that exits with os._exit(). This keeps
    # npm run test and setup-once deterministic even when libraries leave
    # non-daemon threads alive after tests pass.
    wrapper = (
        "import os, sys, pytest; "
        "code = pytest.main(['-p', 'no:cacheprovider'] + sys.argv[1:], plugins=[]); "
        "sys.stdout.flush(); sys.stderr.flush(); os._exit(int(code))"
    )
    cmd = [sys.executable, "-c", wrapper, *default_pytest_args(args)]
    try:
        completed = subprocess.run(cmd, cwd=ROOT, env=env, timeout=PYTEST_TIMEOUT_SECONDS)
        return int(completed.returncode)
    except subprocess.TimeoutExpired:
        print(f"[CSM tests] ERROR: pytest exceeded {PYTEST_TIMEOUT_SECONDS}s timeout", file=sys.stderr, flush=True)
        return 124
    finally:
        cleanup_project_caches()


def main() -> int:
    os.chdir(ROOT)
    return run_pytest(sys.argv[1:], prepare_env())


if __name__ == "__main__":
    sys.exit(main())
