from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def docx_text(path: Path) -> str:
    with ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    return "".join(node.text or "" for node in root.findall(".//w:t", ns))


def test_current_user_guides_are_not_stale():
    html = read("install-guide.html")
    assert "CSM for Word v1.6" in html
    assert "CSM-Setup-v1.6.exe" in html

    instruction = ROOT / "Instrukcja_CSM_v1_6.docx"
    assert instruction.exists()
    text = docx_text(instruction)
    assert "Instrukcja CSM v1.6" in text
    assert "RACHUNEK_BANKOWY" in text
    assert "Obrazy" in text or "obraz" in text.lower()
    assert "v0.4." + "2.1" not in text


def test_package_does_not_keep_obsolete_current_guides():
    obsolete = [
        "Instrukcja_CSM_v0_4_2_1.docx",
        "Instrukcja_CSM_v0_4_2_2.docx",
        "Instrukcja_CSM_v0_4_2_3.docx",
        "WINDOWS-TEST-CHECKLIST-v0.4." + "2.3.md",
    ]
    for rel in obsolete:
        assert not (ROOT / rel).exists(), rel


def test_package_does_not_keep_transient_audit_outputs():
    assert not list(ROOT.glob("npm-audit*.json"))
