from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_polish_release_versions_are_consistent():
    assert 'from version import APP_VERSION' in read('server/api.py')
    assert 'const APP_VERSION = "1.6"' in read('addin/taskpane.js')
    assert '<Version>1.6</Version>' in read('addin/manifest.xml')
    assert '"version": "1.6"' in read('addin/package.json')
    assert 'CSM for Word v1.6' in read('README.md')
    assert '0.4.' + '1.1' not in read('addin/taskpane.js')


def test_report_copy_download_ui_contract():
    html = read('addin/taskpane.html')
    js = read('addin/taskpane.js')
    assert 'btnCopyAnonReport' in html
    assert 'btnDownloadAnonReport' in html
    assert 'Kopiuj raport TXT' in html
    assert 'Kopiuj raport TXT' in html
    assert 'function currentReportPayload()' in js
    assert 'function reportPayloadToText(payload)' in js
    assert 'function downloadAnonymizationReport()' in js
    assert 'bindButton("btnCopyAnonReport", copyAnonymizationReport)' in js
    assert 'bindButton("btnDownloadAnonReport", downloadAnonymizationReport)' in js


def test_v4_response_exposes_report_paths():
    api = read('server/api.py')
    assert 'report_prepare_path: str | None = None' in api
    assert 'report_restore_path: str | None = None' in api
    assert 'report_prepare_path = session_dir / "report_prepare.json"' in api
    assert 'report_restore_path = session_dir / "report_restore.json"' in api
    assert 'report_prepare_path=str(report_prepare_path)' in api
    assert 'report_restore_path=str(report_restore_path)' in api


def test_instruction_and_release_notes_are_current():
    assert (ROOT / 'Instrukcja_CSM_v1_6.docx').exists()
    assert not (ROOT / 'Instrukcja_CSM_v0_4_0_legacy_install_polish.docx').exists()
    assert (ROOT / 'RELEASE-NOTES-v1.6.txt').exists()
    assert 'Jak czytać raport anonimizacji' in read('README.md')
    assert 'report_prepare.json' in read('README.md')
    assert 'report_restore.json' in read('README.md')
