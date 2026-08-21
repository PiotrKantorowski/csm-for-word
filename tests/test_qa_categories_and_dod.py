from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def test_pytest_categories_are_defined_and_enforced():
    pytest_ini = (ROOT / "pytest.ini").read_text(encoding="utf-8")
    conftest = (ROOT / "tests" / "conftest.py").read_text(encoding="utf-8")
    for marker in ("current", "future", "regression"):
        assert f"{marker}:" in pytest_ini
        assert f'"{marker}"' in conftest
    assert "pytest_collection_modifyitems" in conftest
    assert "QA_CATEGORY_MARKERS" in conftest


def test_npm_definition_of_done_scripts_exist():
    root_pkg = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
    addin_pkg = json.loads((ROOT / "addin" / "package.json").read_text(encoding="utf-8"))
    for pkg in (root_pkg, addin_pkg):
        scripts = pkg["scripts"]
        assert "lint" in scripts
        assert "build" in scripts
        assert "test" in scripts
    assert "validate-static.js" in root_pkg["scripts"]["lint"]
    assert "validate-static.js" in root_pkg["scripts"]["build"]
    assert "tests/run_pytest.py" in root_pkg["scripts"]["test"]
    assert "../tests/run_pytest.py" in addin_pkg["scripts"]["test"]


def test_project_pytest_runner_disables_external_plugin_autoload():
    runner = (ROOT / "tests" / "run_pytest.py").read_text(encoding="utf-8")
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in runner
    assert "CSM_BASE_DIR" in runner
    assert "CSM_INSTALL_BACKUPS_DIR" in runner
    assert "CSM_DISABLE_OPEN_FILE" in runner
    assert "subprocess.run" in runner
    assert "os._exit" in runner
    assert "PYTHONDONTWRITEBYTECODE" in runner
    assert "no:cacheprovider" in runner
    assert "default_pytest_args" in runner
    assert "PYTEST_TIMEOUT_SECONDS" in runner


def test_test_runtime_does_not_write_install_backups_into_project_tree():
    redactor = (ROOT / "server" / "redactor.py").read_text(encoding="utf-8")
    assert "CSM_INSTALL_ROOT" in redactor
    assert "CSM_INSTALL_BACKUPS_DIR" in redactor


def test_qa_standards_document_matches_current_architecture():
    text = (ROOT / "docs" / "QA-STANDARDS.md").read_text(encoding="utf-8")
    assert "CSM for Word" in text
    assert "Gemini, React, Tailwind" in text
    assert "current" in text and "future" in text and "regression" in text
    assert "Definition of Done" in text


def test_test_runner_disables_os_file_opening_side_effects():
    api = (ROOT / "server" / "api.py").read_text(encoding="utf-8")
    assert "CSM_DISABLE_OPEN_FILE" in api
    assert "not enabled or os.environ.get" in api


def test_static_validator_rejects_generated_backup_folders():
    validator = (ROOT / "addin" / "scripts" / "validate-static.js").read_text(encoding="utf-8")
    assert "generated backup/session folders" in validator
    assert "backups/" in validator
