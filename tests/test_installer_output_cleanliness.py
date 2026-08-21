from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_installer_output_does_not_ship_stale_exe_artifacts():
    output = ROOT / "installer" / "output"
    stale = sorted(p.name for p in output.glob("*.exe") if "1.6" not in p.name)
    assert stale == [], f"Stale installer EXE artifacts found: {stale}"


def test_source_package_declares_setup_not_included_until_rebuilt():
    note = ROOT / "installer" / "output" / "README-SETUP-NOT-INCLUDED.txt"
    assert note.exists()
    text = note.read_text(encoding="utf-8")
    assert "CSM-Setup-v1.6.exe" in text
    assert "celowo nie ma" in text
