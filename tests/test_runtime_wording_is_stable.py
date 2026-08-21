from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_no_prerelease_wording_in_active_runtime_user_copy() -> None:
    html = _read("addin/taskpane.html")
    js = _read("addin/taskpane.js")
    api = _read("server/api.py")

    assert not re.search(r"\b" + "al" + "pha" + r"\b", html, re.IGNORECASE)
    assert not re.search(r"\b" + "be" + "ta" + r"\b", html, re.IGNORECASE)
    assert "Roundtrip " + "al" + "pha" not in js
    assert "Al" + "pha roundtrip check" not in api
    assert "file_docx_negotiation_" + "al" + "pha" not in api


def test_roundtrip_status_uses_stable_polish_label() -> None:
    js = _read("addin/taskpane.js")
    api = _read("server/api.py")
    assert "Kontrola roundtrip" in js
    assert "Kontrola roundtrip" in api
