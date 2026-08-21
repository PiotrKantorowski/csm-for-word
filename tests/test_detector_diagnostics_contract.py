from __future__ import annotations

import base64
import io
import os
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path


def _import_app():
    os.environ.setdefault("CSM_API_TOKEN", "test-token")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
    from fastapi.testclient import TestClient  # type: ignore
    from api import app  # type: ignore
    return TestClient(app)


def _post(client, url: str, payload: dict):
    return client.post(url, headers={"X-CSM-Token": "test-token"}, json=payload)


def test_no_import_side_effects() -> None:
    src = Path(__file__).resolve().parents[1] / "server"
    install = Path(tempfile.mkdtemp())
    shutil.copytree(src, install / "server")
    (install / "backups").write_text("", encoding="utf-8")
    home = Path(tempfile.mkdtemp())
    old_home = os.environ.get("HOME")
    old_path = list(sys.path)
    old_modules = dict(sys.modules)
    try:
        os.environ["HOME"] = str(home)
        for mod in list(sys.modules):
            if mod in {"redactor", "security", "engine_types", "validators", "legal_lexicon"}:
                del sys.modules[mod]
        sys.path.insert(0, str(install / "server"))
        import redactor  # noqa: F401
        assert hasattr(redactor, "make_replacements")
        assert not (home / "ClaudeSafeModeWord").exists(), "redactor created HOME dirs at import"
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
        sys.path[:] = old_path
        for mod in list(sys.modules):
            if mod not in old_modules and mod in {"redactor", "security", "engine_types", "validators", "legal_lexicon"}:
                del sys.modules[mod]


def test_docx_bomb_xxe_and_ooxml_parts_limits() -> None:
    client = _import_app()
    import redactor  # type: ignore
    import api  # type: ignore
    old_limit = redactor.max_docx_xml_bytes
    package_globals = api.mask_ooxml_package_bytes.__globals__
    old_package_limit = package_globals.get("max_docx_xml_bytes")
    redactor.max_docx_xml_bytes = lambda: 1000
    package_globals["max_docx_xml_bytes"] = lambda: 1000
    try:
        content_types = '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
        doc_xml = '<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>' + ("<w:p><w:r><w:t>x</w:t></w:r></w:p>" * 200) + '</w:body></w:document>'
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("word/document.xml", doc_xml)
        start = time.time()
        r = _post(client, "/mask_docx_package", {"docx_base64": base64.b64encode(buf.getvalue()).decode("ascii")})
        assert r.status_code == 413, r.text
        assert "DOCX package XML zbyt duży po dekompresji" in r.text
        assert time.time() - start < 5
    finally:
        redactor.max_docx_xml_bytes = old_limit
        if old_package_limit is not None:
            package_globals["max_docx_xml_bytes"] = old_package_limit

    xxe_xml = b'<?xml version="1.0"?><!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>&xxe;</w:t></w:r></w:p></w:body></w:document>'
    buf2 = io.BytesIO()
    with zipfile.ZipFile(buf2, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("word/document.xml", xxe_xml)
    r2 = _post(client, "/mask_docx_package", {"docx_base64": base64.b64encode(buf2.getvalue()).decode("ascii")})
    assert r2.status_code == 400, r2.text


def test_error_responses_do_not_leak_pii() -> None:
    client = _import_app()
    for response in (
        _post(client, "/restore", {"map_id": "Jan-Kowalski-PESEL-44051401359"}),
        _post(client, "/mask_docx_package", {"docx_base64": "JanKowalskiNIEJEST=BASE64"}),
        _post(client, "/mask_ooxml", {"ooxml": '<w:document xmlns:w="..."><w:body><w:t>Anna Nowak PESEL 44051401359'}),
    ):
        body = response.text
        for token in ["Kowalski", "PESEL", "44051401359", "JanKowalski", "Anna Nowak", "Nowak"]:
            assert token not in body, f"PII leak {token!r} in {body!r}"


def test_repertorium_decyzja_and_csm_mode() -> None:
    client = _import_app()
    from redactor import make_replacements  # type: ignore
    text = (
        "Akt notarialny Rep. A 1234/2024, Repertorium B nr 9876/2025 "
        "oraz decyzja nr SKO.123.45/2024 i decyzją nr SKO-OL/4101/16/2023 "
        "dotyczą Jana Kowalskiego."
    )
    masked, replacements = make_replacements(text)
    assert "Rep. A 1234/2024" not in masked
    assert "Repertorium B nr 9876/2025" not in masked
    assert "SKO.123.45/2024" not in masked
    assert "SKO-OL/4101/16/2023" not in masked
    assert sum(1 for r in replacements if r.category == "REPERTORIUM") >= 2
    assert sum(1 for r in replacements if r.category == "DECYZJA_ADM") >= 2
    assert client.get("/health").json().get("mode") in {"prod", "dev"}


if __name__ == "__main__":
    test_no_import_side_effects()
    test_docx_bomb_xxe_and_ooxml_parts_limits()
    test_error_responses_do_not_leak_pii()
    test_repertorium_decyzja_and_csm_mode()
    print("OK: detector/diagnostics acceptance tests passed")
