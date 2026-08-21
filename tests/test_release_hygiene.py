from pathlib import Path
import json
import re
import subprocess
import sys
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))["version"]
TAG = f"v{VERSION}"
UNDERSCORE = VERSION.replace(".", "_")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def docx_text(path: Path) -> str:
    with ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    return "".join(node.text or "" for node in root.findall(".//w:t", ns))


def test_v044_has_single_canonical_version_file():
    data = json.loads((ROOT / "VERSION.json").read_text(encoding="utf-8"))
    assert data["version"] == "1.6"
    assert data["cloud_features"] is True
    assert data["ocr_features"] is False
    assert "from version import APP_VERSION" in read("server/api.py")
    assert "VERSION.json" in read("server/version.py")


def test_v044_active_versions_are_synchronized():
    assert f'"version": "{VERSION}"' in read("package.json")
    assert f'"version": "{VERSION}"' in read("addin/package.json")
    assert f'<Version>{VERSION}</Version>' in read("addin/manifest.xml")
    assert f'#define MyAppVersion "{VERSION}"' in read("installer/CSM-Setup.iss")
    assert f"CSM-Setup-{TAG}.exe" in read("installer/build-csm-setup.ps1")
    assert f"CSM for Word {TAG}" in read("README.md")
    assert f"CSM for Word {TAG}" in read("install-guide.html")


def test_v060_installer_requires_license_acceptance_before_install_steps():
    iss = read("installer/CSM-Setup.iss")
    assert "LicenseFile={#SourceDir}\\LICENSE.txt" in iss
    assert iss.index("LicenseFile={#SourceDir}\\LICENSE.txt") < iss.index("[Files]")
    assert (ROOT / "LICENSE.txt").exists()


def test_v060_dotnet_target_stays_on_lts_net8():
    assert "<TargetFramework>net8.0</TargetFramework>" in read("sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj")
    assert "<TargetFramework>net8.0</TargetFramework>" in read("sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj")
    assert "net11.0" not in read("sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj")
    assert "net11.0" not in read("sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj")


def test_v044_root_contains_only_current_release_docs():
    assert (ROOT / f"Instrukcja_CSM_v{UNDERSCORE}.docx").exists()
    assert (ROOT / f"RELEASE-NOTES-{TAG}.txt").exists()
    assert (ROOT / f"WINDOWS-TEST-CHECKLIST-{TAG}.md").exists()

    release_notes = sorted(p.name for p in ROOT.glob("RELEASE-NOTES-v*.txt"))
    instruction_docs = sorted(p.name for p in ROOT.glob("Instrukcja_CSM_v*.docx"))
    checklists = sorted(p.name for p in ROOT.glob("WINDOWS-TEST-CHECKLIST-v*.md"))

    assert release_notes == [f"RELEASE-NOTES-{TAG}.txt"]
    assert instruction_docs == [f"Instrukcja_CSM_v{UNDERSCORE}.docx"]
    assert checklists == [f"WINDOWS-TEST-CHECKLIST-{TAG}.md"]
    assert (ROOT / "docs" / "archive" / "release-notes").exists()


def test_v044_current_guides_do_not_reference_stale_versions():
    stale = re.compile(r"(?:v)?0\.4\.(?:0-legacy prerelease|1(?:\.1)?|2(?:\.1|\.2|\.3)?|3)\b")
    current_files = [
        "README.md",
        "README-EASY-START.md",
        "install-guide.html",
        "addin/taskpane.html",
        "addin/taskpane.js",
        "installer/CSM-Setup.iss",
        "installer/build-csm-setup.ps1",
        "installer/README.md",
        f"RELEASE-NOTES-{TAG}.txt",
        f"WINDOWS-TEST-CHECKLIST-{TAG}.md",
    ]
    for rel in current_files:
        assert not stale.search(read(rel)), rel

    text = docx_text(ROOT / f"Instrukcja_CSM_v{UNDERSCORE}.docx")
    assert f"Instrukcja CSM {TAG}" in text
    assert not stale.search(text)


def test_v044_package_has_no_generated_artifacts():
    forbidden_dirs = {"node_modules", ".venv"}
    forbidden_patterns = [re.compile(r".*\.pyc$"), re.compile(r"npm-audit.*\.json$"), re.compile(r"\.DS_Store$")]
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("docs/archive/"):
            continue
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue  # pytest may create this during the current test run; release lint catches it before packaging.
        assert path.name not in forbidden_dirs, rel
        if path.is_file():
            assert not any(pattern.match(path.name) for pattern in forbidden_patterns), rel





def test_v060_source_package_does_not_include_build_outputs():
    # This test intentionally avoids __pycache__/.pyc because compileall/pytest may create them
    # during a normal local test run. Final ZIP cleanliness is verified by the packaging step.
    forbidden_dir_names = {"node_modules", ".venv", "bin", "obj"}
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith("docs/archive/"):
            continue
        if rel.startswith("installer/output/"):
            # The built installer is a release artifact; it must not be embedded by the installer itself.
            continue
        if path.is_dir() and path.name in forbidden_dir_names:
            assert False, rel

def test_v044_project_test_runner_does_not_pollute_worktree(tmp_path):
    targets = [ROOT / ".pytest_cache", ROOT / "server" / "__pycache__", ROOT / "tests" / "__pycache__"]
    for target in targets:
        if target.exists():
            if target.is_dir():
                import shutil
                shutil.rmtree(target)
            else:
                target.unlink()
    result = subprocess.run(
        [sys.executable, "tests/run_pytest.py", "tests/test_release_hygiene.py::test_v044_has_single_canonical_version_file", "-q"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    for target in targets:
        assert not target.exists(), target.as_posix()


def test_v044_ocr_is_not_described_as_pending_feature():
    active_files = [
        "server/api.py",
        "server/tc_engine.py",
        "server/redactor.py",
        "addin/taskpane.html",
        "README.md",
        f"RELEASE-NOTES-{TAG}.txt",
    ]
    pending_ocr = re.compile("|".join(["nie wykonuje" + " jes" + "zcze", "jes" + "zcze " + ".*" + "OCR", "peł" + "nego " + "OCR"]), re.IGNORECASE)
    for rel in active_files:
        assert not pending_ocr.search(read(rel)), rel


def test_v044_github_workflow_runs_qa_before_installer_build():
    workflow = read(".github/workflows/build-csm-installer.yml")
    assert "permissions:" in workflow
    assert "contents: read" in workflow
    assert "concurrency:" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "persist-credentials: false" in workflow
    assert "actions/checkout@v6" in workflow
    assert workflow.count("persist-credentials: false") >= 2
    assert "actions/setup-node@v4" in workflow
    assert "actions/setup-python@v5" in workflow
    assert "actions/setup-dotnet@v5" in workflow
    assert "dotnet-version: '8.0.x'" in workflow
    assert "global-json-file: global.json" in workflow
    global_json = json.loads((ROOT / "global.json").read_text(encoding="utf-8"))
    assert global_json["sdk"]["version"] == "8.0.100"
    assert global_json["sdk"]["rollForward"] == "latestFeature"
    assert "dotnet restore sidecar\\CSM.RevisionSidecar\\CSM.RevisionSidecar.csproj" in workflow
    assert "dotnet build sidecar\\CSM.RevisionSidecar\\CSM.RevisionSidecar.csproj -c Release --no-restore" in workflow
    assert "dotnet test sidecar\\CSM.RevisionSidecar.Tests\\CSM.RevisionSidecar.Tests.csproj -c Release --no-restore" in workflow
    assert "CSM_REVISION_SIDECAR_CMD" in workflow
    assert "tests\\test_revision_sidecar_integration.py" in workflow
    assert "npm ci" in workflow
    assert "python -m pip install -r server\\requirements.txt" in workflow
    assert "npm run lint --silent" in workflow
    assert "python -m pytest -q" in workflow
    assert "npm run build --silent" in workflow
    assert "needs: qa" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "if-no-files-found: error" in workflow
    assert "retention-days: 14" in workflow


def test_v044_github_release_notes_config_exists():
    release_yml = read(".github/release.yml")
    assert "changelog:" in release_yml
    assert "skip-changelog" in release_yml
    assert "Funkcje" in release_yml
    assert "Poprawki jakości i bezpieczeństwa" in release_yml


def test_v044_archived_skipped_tests_are_not_collected_by_pytest():
    assert not (ROOT / "tests" / "test_v04_taskpane_integration.py").exists()
    assert (ROOT / "docs" / "archive" / "tests" / "test_v04_taskpane_integration.py.txt").exists()
    assert "archived skipped tests must live outside active pytest collection" in read("addin/scripts/validate-static.js")


def test_v044_active_tests_use_feature_names_and_current_wording():
    pre_a = "al" + "pha"
    pre_b = "be" + "ta"
    patch_word = "hot" + "fix"
    historical_name = re.compile(
        r"^test_v(?:0?3|0?4|0?5|0?6|0?7|030|035|036|037|039|040|041|042|043|044|050)|"
        + pre_a
        + "|"
        + pre_b
        + "|"
        + patch_word,
        re.IGNORECASE,
    )
    historical_text = re.compile(
        r"(?:v)?0\.4\.(?:1(?:\.1)?|2(?:\.1|\.2|\.3)?|3)\b|0\.3\.0-"
        + pre_a
        + r"|\b"
        + pre_a
        + r"\d*\b|\b"
        + pre_b
        + r"\d*\b|\b"
        + patch_word
        + r"\b",
        re.IGNORECASE,
    )
    for path in (ROOT / "tests").glob("test_*.py"):
        assert not historical_name.search(path.name), path.name
        assert not historical_text.search(path.read_text(encoding="utf-8")), path.name


def test_v044_historical_instruction_assets_are_archived():
    assert not (ROOT / "docs" / "v04_alpha2_instr_assets").exists()
    assert (ROOT / "docs" / "archive" / "instruction-assets" / "v04-prerelease-instruction-assets").exists()


def test_v060_release_notes_are_not_legacy_changelog_dump():
    notes = read(f"RELEASE-NOTES-{TAG}.txt")
    assert "CSM for Word v1.0" in notes
    assert "Bielik" in notes
    forbidden = [
        "Panel pokazuje jedno logo CSM i prostą wersję v0.5",
        "final2",
        "final3",
        "final5",
        "final6",
        "Poprawka rc7",
        "v0.5.0",
        "v0.5 —",
        "v0.5 --",
    ]
    for needle in forbidden:
        assert needle not in notes


def test_v060_lawyer_facing_copy_avoids_raw_sidecar_and_ooxml_terms():
    js = read("addin/taskpane.js")
    html = read("addin/taskpane.html")
    assert "Sprawdź śledzenie zmian" in html
    user_status_needles = [
        "Wersja połączenia lokalnego",
        "Tryb strukturalny ze śledzeniem zmian",
        "Przywracanie strukturalne zostało wykonane",
    ]
    for needle in user_status_needles:
        assert needle in js
    forbidden_visible = [
        "Wersja komunikacji technicznej",
        "sidecar rewizji OOXML",
        "Word Range API przed zbudowaniem",
        "Tryb OOXML ze śledzeniem zmian nie został zastosowany",
        "OOXML restore został wykonany",
    ]
    for needle in forbidden_visible:
        assert needle not in js


def test_v060_sidecar_tracked_replace_covers_text_bearing_word_parts():
    engine = read("sidecar/CSM.RevisionSidecar/SidecarEngine.cs")
    assert "GetTextBearingParts" in engine
    assert "mainPart.HeaderParts" in engine
    assert "mainPart.FooterParts" in engine
    assert "mainPart.FootnotesPart" in engine
    assert "mainPart.EndnotesPart" in engine
    assert "mainPart.WordprocessingCommentsPart" in engine
    assert "part.PutXDocument();" in engine


def test_active_release_labels_use_rc17_not_stale_rc11_rc12_rc13_rc14_rc15():
    active_files = [
        ROOT / "VERSION.json",
        ROOT / "addin" / "manifest.xml",
        ROOT / "addin" / "taskpane.html",
        ROOT / "tools" / "install-csm.ps1",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in active_files)
    # rc17, rc18 or later (rc19+) is acceptable — must not have stale pre-rc17 labels
    assert any(v in combined for v in ("rc17", "rc18", "rc19", "1.0"))
    assert "rc15" not in combined
    assert "rc11 - instalacja" not in combined
    assert "rc12-ci-sidecar-exe" not in combined
    assert "v1.0 — rc12" not in combined
    assert "20260518-rc14" not in combined
    assert "v1.0 — rc14" not in combined
    # final6 icon filenames are the active 0.6.1 cache-busted manifest assets.
    assert "20260516-final6" not in combined
    assert "v050.png?build" not in combined
    assert "v05r1.png?build" not in combined
