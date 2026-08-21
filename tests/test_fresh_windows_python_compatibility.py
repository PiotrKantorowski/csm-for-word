from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8')


def test_setup_installs_runtime_requirements_without_test_runner_or_node():
    text = read('tools/setup-once.ps1')
    assert 'requirements-runtime.txt' in text
    assert '--only-binary=:all:' in text
    assert 'tests\\run_pytest.py' not in text
    assert 'run_pytest.py' not in text
    assert 'npm' not in text.lower()
    assert 'npx' not in text.lower()


def test_setup_requires_python_312_for_cp312_offline_wheelhouse():
    text = read('tools/setup-once.ps1')
    assert 'Python.Python.3.12' in text
    assert 'Info.Minor -ne 12' in text
    assert 'cp312' in text
    assert '3.10-3.13' not in text
    assert '-3.11' not in text and '-3.13' not in text and '-3.10' not in text


def test_autostart_uses_valid_windows_runlevel_name():
    text = read('tools/register-autostart.ps1')
    assert '-RunLevel Limited' in text
    assert 'LeastPrivilege' not in text
