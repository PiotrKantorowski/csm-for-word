"""QA test category policy for CSM.

Every collected test receives exactly one QA category marker:
- current: verifies the currently supported CSM workflow,
- future: documents forward-compatible or planned behavior,
- regression: protects behavior fixed in earlier releases.

The mapping is intentionally filename-based so regression tests do not need noisy
per-function decorators. New tests can still set one marker explicitly.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Keep ad-hoc `python -m pytest` runs from writing emergency backups, maps
# or opened-file side effects into the project tree. The dedicated
# tests/run_pytest.py runner also sets these variables; this fallback only
# applies when a developer invokes pytest directly.
_TEST_RUNTIME = Path(tempfile.mkdtemp(prefix="csm-pytest-direct-"))
os.environ.setdefault("CSM_BASE_DIR", str(_TEST_RUNTIME / "base"))
os.environ.setdefault("CSM_INSTALL_ROOT", str(_TEST_RUNTIME / "install"))
os.environ.setdefault("CSM_INSTALL_BACKUPS_DIR", str(_TEST_RUNTIME / "install" / "backups"))
os.environ.setdefault("CSM_DISABLE_OPEN_FILE", "1")
# Disable Bielik AI for all tests by default — if CSMW_ENABLE_BIELIK=1 is set
# in the user's environment (e.g. after setup-once.ps1), tests that don't
# explicitly mock the Ollama endpoint would try to call a live model, turning
# performance-sensitive tests into network-timeout hangs.
# Tests that specifically validate Bielik behaviour use monkeypatch to override.
os.environ["CSMW_ENABLE_BIELIK"] = "0"

import pytest

QA_CATEGORY_MARKERS = ("current", "future", "regression")

CURRENT_FILE_HINTS = (
    # Current means supported by the current release, not necessarily created in this release.
    "current_workflow",
    "frontend_backend_ux_contract",
    "install_polish",
    "ux_polish",
    "negotiation_and_installer",
    "ui_latest_link",
    "taskpane_integration",
    "selftest",
)

FUTURE_FILE_HINTS = (
    "future",
    "roadmap",
)


def _category_for_path(path: str) -> str:
    lower = path.replace("\\", "/").lower()
    if any(hint in lower for hint in FUTURE_FILE_HINTS):
        return "future"
    if any(hint in lower for hint in CURRENT_FILE_HINTS):
        return "current"
    return "regression"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        explicit = [name for name in QA_CATEGORY_MARKERS if item.get_closest_marker(name)]
        if len(explicit) > 1:
            raise pytest.UsageError(f"Test {item.nodeid} has multiple QA category markers: {explicit}")
        if not explicit:
            item.add_marker(getattr(pytest.mark, _category_for_path(str(item.path))))
