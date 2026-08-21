from __future__ import annotations

import sys
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_TEST_RUNTIME = Path(tempfile.mkdtemp(prefix="csm-selftest-"))
os.environ.setdefault("CSM_BASE_DIR", str(_TEST_RUNTIME / "base"))
os.environ.setdefault("CSM_INSTALL_ROOT", str(_TEST_RUNTIME / "install"))
os.environ.setdefault("CSM_INSTALL_BACKUPS_DIR", str(_TEST_RUNTIME / "install" / "backups"))
os.environ.setdefault("CSM_DISABLE_OPEN_FILE", "1")
os.environ["CSM_API_TOKEN"] = "test-token"
sys.path.insert(0, str(ROOT / "server"))

from fastapi.testclient import TestClient

from api import app, MAX_TEXT_BYTES_DEFAULT
from redactor import make_replacements, mask_ooxml, restore_ooxml, save_map, load_map, find_residual_risks, placeholder_report




def post(client: TestClient, url: str, **kwargs):
    headers = kwargs.pop("headers", {}) or {}
    headers["X-CSM-Token"] = "test-token"
    return client.post(url, headers=headers, **kwargs)

def restore_text(masked: str, replacements: list[dict]) -> str:
    restored = masked
    for r in sorted(replacements, key=lambda item: len(item["placeholder"]), reverse=True):
        restored = restored.replace(r["placeholder"], r["original"])
    return restored


def test_core_roundtrip() -> None:
    text = (
        "Jan Kowalski, PESEL 44051401359, NIP 526-000-12-46, "
        "email jan@example.com, tel +48 123 456 789, "
        "sygn. akt I C 123/24, Sąd Rejonowy w Rzeszowie, ul. Długa 10."
    )
    masked, replacements = make_replacements(text)
    assert "Jan Kowalski" not in masked
    assert "44051401359" not in masked
    assert "jan@example.com" not in masked
    restored = masked
    for r in sorted(replacements, key=lambda item: len(item.placeholder), reverse=True):
        restored = restored.replace(r.placeholder, r.original)
    assert restored == text


def test_pesel_like_value_is_masked_even_if_checksum_fails() -> None:
    text = "Jan Kowalski, PESEL 80010112345, e-mail jan@example.com"
    masked, replacements = make_replacements(text)
    assert "80010112345" not in masked
    assert any(r.category == "PESEL" for r in replacements)


def test_company_entities_are_masked_for_professional_secrecy() -> None:
    text = (
        "ABC sp. z o.o. zawarła umowę z XYZ S.A. oraz Fundacja Dobra Pomoc. "
        "Usługi realizuje także ZXCV sp. z o.o., dalej jako ZXCV. Kontakt: zarzad@abc.pl, KRS 0000123456."
    )
    masked, replacements = make_replacements(text)
    assert "ABC sp. z o.o." not in masked
    assert "XYZ S.A." not in masked
    assert "Fundacja Dobra Pomoc" not in masked
    assert "ZXCV" not in masked
    assert sum(1 for r in replacements if r.category in ("COMPANY", "COMPANY_ALIAS", "ALIAS")) >= 3


def test_ooxml_replaces_values_split_across_runs() -> None:
    ooxml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Jan </w:t></w:r><w:r><w:t>Kowalski, PESEL </w:t></w:r><w:r><w:t>80010112345, umowa z ABC </w:t></w:r><w:r><w:t>sp. z o.o.</w:t></w:r></w:p></w:body></w:document>'''
    masked_ooxml, replacements = mask_ooxml(ooxml)
    assert "Jan Kowalski" not in masked_ooxml
    assert "80010112345" not in masked_ooxml
    assert "ABC" not in masked_ooxml
    assert any(r.category == "PERSON" for r in replacements)
    assert any(r.category == "PESEL" for r in replacements)
    assert any(r.category == "COMPANY" for r in replacements)
    map_id = save_map(replacements, original_ooxml=ooxml)
    payload = load_map(map_id)
    restored_ooxml = restore_ooxml(masked_ooxml, payload["replacements"])
    assert "Jan Kowalski" in restored_ooxml
    assert "80010112345" in restored_ooxml
    assert "ABC sp. z o.o." in restored_ooxml


def test_api_roundtrip() -> None:
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["version"] == "1.6"

    text = "Anna Nowak PESEL 44051401359 e-mail anna.nowak@example.com"
    mask = post(client, "/mask", json={"text": text})
    assert mask.status_code == 200
    masked_payload = mask.json()
    assert masked_payload["version"] == "1.6"
    assert "Anna Nowak" not in masked_payload["masked_text"]
    assert "map_id" in masked_payload

    restore = post(client, "/restore", json={"map_id": masked_payload["map_id"]})
    assert restore.status_code == 200
    restored = restore_text(masked_payload["masked_text"], restore.json()["replacements"])
    assert restored == text


def test_v022_api_rejects_oversized_text_payloads() -> None:
    client = TestClient(app)
    too_large = "x" * (MAX_TEXT_BYTES_DEFAULT + 1)
    for endpoint in ("/mask", "/scan"):
        response = post(client, endpoint, json={"text": too_large})
        assert response.status_code == 413, f"{endpoint} accepted oversized text"
        assert response.json()["detail"] == "Tekst przekracza limit 2 MB."


def test_v022_api_accepts_text_at_byte_limit() -> None:
    client = TestClient(app)
    at_limit = "x" * MAX_TEXT_BYTES_DEFAULT
    response = post(client, "/scan", json={"text": at_limit})
    assert response.status_code == 200, response.text


def test_v024_docx_revision_report_detects_tracked_changes() -> None:
    import base64
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", """<?xml version='1.0' encoding='UTF-8'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/></Types>""")
        zf.writestr("word/document.xml", """<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:ins w:id='1' w:author='Tester'><w:r><w:t>Jan Kowalski</w:t></w:r></w:ins></w:p></w:body></w:document>""")
    payload = base64.b64encode(buf.getvalue()).decode("ascii")
    client = TestClient(app)
    response = post(client, "/docx_revision_report", json={"docx_base64": payload})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["version"] == "1.6"
    assert data["has_tracked_changes"] is True
    assert "word/document.xml" in data["revision_files"]


def test_api_ooxml_roundtrip() -> None:
    client = TestClient(app)
    ooxml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Anna </w:t></w:r><w:r><w:t>Nowak i XYZ S.A. oraz ZXCV</w:t></w:r></w:p></w:body></w:document>'''
    mask = post(client, "/mask_ooxml", json={"ooxml": ooxml})
    assert mask.status_code == 200
    data = mask.json()
    assert "Anna Nowak" not in data["ooxml"]
    restore = post(client, "/restore_ooxml", json={"map_id": data["map_id"], "ooxml": data["ooxml"]})
    assert restore.status_code == 200
    restored = restore.json()["ooxml"]
    assert "Anna Nowak" in restored
    assert "XYZ S.A." in restored
    assert "ZXCV" in restored
    original = post(client, "/original_ooxml", json={"map_id": data["map_id"]})
    assert original.status_code == 200
    assert original.json()["ooxml"] == ooxml


def test_contract_context_aliases_and_inflections() -> None:
    text = (
        "Umowa zawarta pomiędzy ABC Marketing sp. z o.o., dalej jako \"ABC\", a Jan Kowalski. "
        "Zamawiający zleca Wykonawcy wykonanie usług. "
        "ABC przekaże dokumenty ABC-u oraz Janowi Kowalskiemu. "
        "Kontakt z Janem Kowalskim pod adresem jan@abc.pl."
    )
    masked, replacements = make_replacements(text)
    assert "ABC Marketing" not in masked
    assert "ABC-u" not in masked
    assert "Janowi Kowalskiemu" not in masked
    assert "Janem Kowalskim" not in masked
    assert "jan@abc.pl" not in masked
    assert "Zamawiający" in masked
    assert "Wykonawcy" in masked
    assert any(r.category in ("COMPANY_ALIAS", "ALIAS") for r in replacements)
    assert any(r.original == "Janowi Kowalskiemu" for r in replacements)
    assert any(r.original == "Janem Kowalskim" for r in replacements)


def test_ooxml_contract_alias_roundtrip() -> None:
    ooxml = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>ABC Marketing </w:t></w:r><w:r><w:t>sp. z o.o., dalej jako "ABC". Dokumenty ABC-u przekaże Janowi Kowalskiemu.</w:t></w:r></w:p></w:body></w:document>'''
    masked_ooxml, replacements = mask_ooxml(ooxml)
    assert "ABC Marketing" not in masked_ooxml
    assert "ABC-u" not in masked_ooxml
    assert "Janowi Kowalskiemu" not in masked_ooxml
    map_id = save_map(replacements, original_ooxml=ooxml)
    payload = load_map(map_id)
    restored_ooxml = restore_ooxml(masked_ooxml, payload["replacements"])
    assert "ABC Marketing sp. z o.o." in restored_ooxml
    assert "ABC-u" in restored_ooxml
    assert "Janowi Kowalskiemu" in restored_ooxml


def test_v011_professional_secrecy_checklist() -> None:
    text = (
        "Zamawiający: Alfa Test sp. z o.o. z siedzibą w Krakowie, dalej jako \"AB\". "
        "Wykonawca: Fundacja Dobry Start, kontakt: Anna Nowak, anna.nowak@alfatest.pl, domena alfatest.pl. "
        "Usługi dotyczą Projekt Aurora, System Klient24 oraz Platforma Partnera. "
        "Pełnomocnik Jan Kowalski będzie działał w imieniu AB. "
        "AB-u dotyczy także portal https://alfatest.pl/panel. Dowód ABA300000, paszport AB3000000."
    )
    masked, replacements = make_replacements(text)
    forbidden = [
        "Alfa Test", "Fundacja Dobry Start", "AB-u", "anna.nowak@alfatest.pl",
        "alfatest.pl", "Projekt Aurora", "System Klient24", "Platforma Partnera",
        "Jan Kowalski", "Anna Nowak", "ABA300000", "AB3000000"
    ]
    for item in forbidden:
        assert item not in masked, f"not masked: {item}\n{masked}"
    assert any(r.category in {"COMPANY", "CONTRACTOR"} for r in replacements)
    assert any(r.category == "EMAIL" for r in replacements)
    assert any(r.category in {"DOMAIN", "DOMAIN_ALIAS", "URL"} for r in replacements)
    assert any(r.category == "PROJECT" for r in replacements)
    assert any(r.category == "PERSON" for r in replacements)
    assert any(r.category == "IDCARD_PL" for r in replacements)
    assert any(r.category == "PASSPORT_PL" for r in replacements)


def test_v011_warnings_do_not_repeat_values() -> None:
    warnings = find_residual_risks("Pozostało Potencjalne Imie i System Xyz oraz domena testowa.pl")
    joined = " ".join(warnings)
    assert "Potencjalne" not in joined
    assert "testowa.pl" not in joined
    assert any("potencjalne" in w for w in warnings)



def test_v012_identity_ledger_clusters_aliases() -> None:
    text = (
        "Alfa Test sp. z o.o., dalej jako \"AB\". "
        "AB wykona usługę, dokumenty AB-u trafią do alfatest.pl oraz biuro@alfatest.pl."
    )
    masked, replacements = make_replacements(text)
    assert "Alfa Test" not in masked
    assert "AB-u" not in masked
    assert "alfatest.pl" not in masked
    company_placeholders = {r.placeholder for r in replacements if r.category in {"COMPANY", "COMPANY_ALIAS", "ALIAS"}}
    # Identity ledger should reduce random placeholder drift for the same commercial identity.
    assert company_placeholders and all(ph.startswith("[FIRMA_1") for ph in company_placeholders)


def test_v012_engine_records_version_in_map() -> None:
    masked, replacements = make_replacements("Jan Kowalski i Alfa Test sp. z o.o.")
    map_id = save_map(replacements, original_text="Jan Kowalski i Alfa Test sp. z o.o.")
    payload = load_map(map_id)
    assert payload.get("engine_version") == "0.2.48-rc19-pl-gazetteers"



def test_v021_ooxml_parts_headers_and_body_roundtrip() -> None:
    client = TestClient(app)
    parts = {
        "body": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Umowa z ABC sp. z o.o. i Janem Kowalskim.</w:t></w:r></w:p></w:body></w:document>',
        "section0_header0": '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>Klient: ABC sp. z o.o.</w:t></w:r></w:p></w:hdr>',
        "section0_footer0": '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>kontakt@abc.pl</w:t></w:r></w:p></w:ftr>',
    }
    mask = post(client, "/mask_ooxml_parts", json={"parts": parts})
    assert mask.status_code == 200, mask.text
    data = mask.json()
    joined = "\n".join(data["parts"].values())
    assert "ABC sp. z o.o." not in joined
    assert "kontakt@abc.pl" not in joined
    report = post(client, "/placeholder_report", json={"map_id": data["map_id"], "parts": data["parts"]})
    assert report.status_code == 200
    pre = report.json()["placeholder_report"]
    assert pre["found_total"] > 0
    restore = post(client, "/restore_ooxml_parts", json={"map_id": data["map_id"], "parts": data["parts"]})
    assert restore.status_code == 200, restore.text
    restored = restore.json()["parts"]
    restored_joined = "\n".join(restored.values())
    assert "ABC sp. z o.o." in restored_joined
    assert "kontakt@abc.pl" in restored_joined
    rr = restore.json()["restore_report"]
    assert rr["restored_occurrences"] > 0
    assert rr["leftover_total_after_restore"] == 0


def test_v021_placeholder_validation_detects_modified_placeholders() -> None:
    masked, replacements = make_replacements("Jan Kowalski i ABC sp. z o.o.")
    map_id = save_map(replacements, original_text="Jan Kowalski i ABC sp. z o.o.")
    payload = load_map(map_id)
    broken = masked.replace("[OSOBA_1]", "[OSOBA_99]")
    report = placeholder_report(broken, payload["replacements"])
    assert report["missing_total"] >= 1
    assert report["unknown_total"] >= 1


def test_v022_docx_package_masks_comments_footnotes_and_metadata() -> None:
    import base64
    import io
    import zipfile
    client = TestClient(app)
    files = {
        "[Content_Types].xml": """<?xml version='1.0' encoding='UTF-8'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/></Types>""",
        "word/document.xml": """<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>Umowa z ABC sp. z o.o.</w:t></w:r></w:p></w:body></w:document>""",
        "word/comments.xml": """<w:comments xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:comment w:id='0'><w:p><w:r><w:t>Komentarz: Anna Nowak, anna@abc.pl</w:t></w:r></w:p></w:comment></w:comments>""",
        "word/footnotes.xml": """<w:footnotes xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:footnote w:id='2'><w:p><w:r><w:t>Przypis: Jan Kowalski i Projekt Aurora.</w:t></w:r></w:p></w:footnote></w:footnotes>""",
        "docProps/core.xml": """<cp:coreProperties xmlns:cp='http://schemas.openxmlformats.org/package/2006/metadata/core-properties' xmlns:dc='http://purl.org/dc/elements/1.1/'><dc:creator>Piotr Kantorowski</dc:creator><dc:title>Sprawa ABC sp. z o.o.</dc:title></cp:coreProperties>""",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    mask = post(client, "/mask_docx_package", json={"docx_base64": b64})
    assert mask.status_code == 200, mask.text
    data = mask.json()
    raw = base64.b64decode(data["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
        joined = "\n".join(z.read(name).decode("utf-8") for name in files)
    for forbidden in ["ABC sp. z o.o.", "Anna Nowak", "anna@abc.pl", "Jan Kowalski", "Projekt Aurora", "Piotr Kantorowski"]:
        assert forbidden not in joined, f"not masked in DOCX package: {forbidden}"
    assert data["package_report"]["coverage"]["comments"] is True
    assert data["package_report"]["coverage"]["footnotes"] is True
    assert data["package_report"]["coverage"]["metadata"] >= 1
    restore = post(client, "/restore_docx_package", json={"map_id": data["map_id"], "docx_base64": data["docx_base64"]})
    assert restore.status_code == 200, restore.text
    restored_raw = base64.b64decode(restore.json()["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(restored_raw), "r") as z:
        restored_joined = "\n".join(z.read(name).decode("utf-8") for name in files)
    assert "Anna Nowak" in restored_joined
    assert "ABC sp. z o.o." in restored_joined
    assert "Piotr Kantorowski" in restored_joined


def test_v021_map_is_wrapped_in_v2_envelope() -> None:
    masked, replacements = make_replacements("Jan Kowalski")
    map_id = save_map(replacements, original_text="Jan Kowalski")
    path = Path(os.environ["CSM_BASE_DIR"]) / "maps" / f"{map_id}.json"
    raw = path.read_text(encoding="utf-8")
    assert "claude-safe-mode-map-v2" in raw
    payload = load_map(map_id)
    assert payload["map_id"] == map_id



def test_v024_legal_headings_are_not_masked_but_party_codes_are() -> None:
    text = (
        "§ 4 Klauzula Poufności. Informacje Poufne oraz Ogólne Warunki i Świadczenia Usług "
        "nie powinny być maskowane. Kodeksu Cywilnego i Zarząd Klienta także nie. "
        "ZXCV sp. z o.o., zwany dalej ZXCV, realizuje usługi. Dokumenty ZXCV-u są załączone."
    )
    masked, replacements = make_replacements(text)
    for public_term in ["Klauzula Poufności", "Informacje Poufne", "Ogólne Warunki", "Świadczenia Usług", "Kodeksu Cywilnego", "Zarząd Klienta"]:
        assert public_term in masked, f"legal term should remain visible: {public_term} -> {masked}"
    for confidential in ["ZXCV sp. z o.o.", "ZXCV-u"]:
        assert confidential not in masked, f"party identifier not masked: {confidential}"
    assert any(r.category in {"COMPANY", "COMPANY_CODE", "COMPANY_ALIAS"} for r in replacements)


def test_v024_docx_package_masks_comment_author_attributes() -> None:
    import base64, io, zipfile
    client = TestClient(app)
    files = {
        "[Content_Types].xml": "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/></Types>",
        "word/document.xml": "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>Umowa z ZXCV sp. z o.o.</w:t></w:r></w:p></w:body></w:document>",
        "word/comments.xml": "<w:comments xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:comment w:id='0' w:author='Piotr Kantorowski' w:initials='PK'><w:p><w:r><w:t>Komentarz: Jan Kowalski, jan@zxcv.pl</w:t></w:r></w:p></w:comment></w:comments>",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    mask = post(client, "/mask_docx_package", json={"docx_base64": b64})
    assert mask.status_code == 200, mask.text
    raw = base64.b64decode(mask.json()["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
        comments = z.read("word/comments.xml").decode("utf-8")
        document = z.read("word/document.xml").decode("utf-8")
    assert "Piotr Kantorowski" not in comments
    assert "Jan Kowalski" not in comments
    assert "jan@zxcv.pl" not in comments
    assert "ZXCV sp. z o.o." not in document


def test_v025_settings_track_revisions_removed_and_legal_terms_keep_visible() -> None:
    import base64, io, zipfile
    client = TestClient(app)
    files = {
        "[Content_Types].xml": "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/></Types>",
        "word/document.xml": "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p><w:r><w:t>Przedmiot Umowy, Ogólne Warunki, Informacje Poufne i Kodeks Cywilny pozostają widoczne. ZXCV sp. z o.o., dalej jako ZXCV, realizuje usługę dla ZXCV-u.</w:t></w:r></w:p></w:body></w:document>",
        "word/settings.xml": "<w:settings xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:trackRevisions/><w:doNotTrackMoves/><w:doNotTrackFormatting/></w:settings>",
        "word/comments.xml": "<w:comments xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:comment w:id='0' w:author='Piotr Kantorowski' w:initials='PK'><w:p><w:r><w:t>Anna Nowak z ZXCV napisała do anna@zxcv.pl</w:t></w:r></w:p></w:comment></w:comments>",
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    mask = post(client, "/mask_docx_package", json={"docx_base64": base64.b64encode(buf.getvalue()).decode("ascii")})
    assert mask.status_code == 200, mask.text
    raw = base64.b64decode(mask.json()["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(raw), "r") as z:
        document = z.read("word/document.xml").decode("utf-8")
        settings = z.read("word/settings.xml").decode("utf-8")
        comments = z.read("word/comments.xml").decode("utf-8")
    for public_term in ["Przedmiot Umowy", "Ogólne Warunki", "Informacje Poufne", "Kodeks Cywilny"]:
        assert public_term in document
    assert "ZXCV" not in document
    assert "trackRevisions" not in settings
    assert "doNotTrack" not in settings
    assert "Piotr Kantorowski" not in comments
    assert "Anna Nowak" not in comments
    assert "anna@zxcv.pl" not in comments




def test_v025_docx_package_preserves_revision_markup_and_masks_revision_text() -> None:
    import base64, io, zipfile
    client = TestClient(app)
    files = {
        "[Content_Types].xml": "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/></Types>",
        "word/document.xml": (
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p>"
            "<w:ins w:id='1' w:author='Tester'><w:r><w:t>Jan Kowalski</w:t></w:r></w:ins>"
            "<w:del w:id='2' w:author='Tester'><w:r><w:delText>Anna Nowak</w:delText></w:r></w:del>"
            "<w:r><w:t> oraz ZXCV sp. z o.o.</w:t></w:r>"
            "</w:p></w:body></w:document>"
        ),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    source_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    mask = post(client, "/mask_docx_package", json={"docx_base64": source_b64})
    assert mask.status_code == 200, mask.text
    data = mask.json()
    masked_raw = base64.b64decode(data["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(masked_raw), "r") as z:
        document = z.read("word/document.xml").decode("utf-8")
    assert ":ins" in document or "<w:ins" in document
    assert ":del" in document or "<w:del" in document
    assert "Jan Kowalski" not in document
    assert "Anna Nowak" not in document
    assert "ZXCV sp. z o.o." not in document

    report = post(client, "/docx_revision_report", json={"docx_base64": data["docx_base64"]})
    assert report.status_code == 200, report.text
    assert report.json()["has_tracked_changes"] is True

    restore = post(client, "/restore_docx_package", json={"map_id": data["map_id"], "docx_base64": data["docx_base64"]})
    assert restore.status_code == 200, restore.text
    restored_raw = base64.b64decode(restore.json()["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(restored_raw), "r") as z:
        restored_document = z.read("word/document.xml").decode("utf-8")
    assert ":ins" in restored_document or "<w:ins" in restored_document
    assert ":del" in restored_document or "<w:del" in restored_document
    assert "Jan Kowalski" in restored_document
    assert "Anna Nowak" in restored_document
    assert "ZXCV sp. z o.o." in restored_document



def test_v026_docx_package_restore_reports_missing_placeholders() -> None:
    import base64, io, zipfile
    client = TestClient(app)
    files = {
        "[Content_Types].xml": "<?xml version='1.0'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='xml' ContentType='application/xml'/></Types>",
        "word/document.xml": (
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p>"
            "<w:ins w:id='1' w:author='Tester'><w:r><w:t>Jan Kowalski</w:t></w:r></w:ins>"
            "<w:r><w:t> oraz Anna Nowak</w:t></w:r>"
            "</w:p></w:body></w:document>"
        ),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    mask = post(client, "/mask_docx_package", json={"docx_base64": base64.b64encode(buf.getvalue()).decode("ascii")})
    assert mask.status_code == 200, mask.text
    data = mask.json()
    masked_raw = base64.b64decode(data["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(masked_raw), "r") as zin:
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                raw = zin.read(info.filename)
                if info.filename == "word/document.xml":
                    xml = raw.decode("utf-8")
                    # Symulacja: Claude zamienił jeden placeholder na inny, nieznany mapie.
                    xml = xml.replace("[OSOBA_1]", "[OSOBA_99]", 1)
                    raw = xml.encode("utf-8")
                zout.writestr(info, raw)
    broken_b64 = base64.b64encode(out.getvalue()).decode("ascii")
    restore = post(client, "/restore_docx_package", json={"map_id": data["map_id"], "docx_base64": broken_b64})
    assert restore.status_code == 200, restore.text
    rr = restore.json()["restore_report"]
    assert rr["missing_total"] >= 1
    assert "[OSOBA_1]" in rr["missing_placeholders"]
    assert rr["unknown_total"] >= 1
    assert "[OSOBA_99]" in rr["unknown_placeholders"]
    assert rr["leftover_total_after_restore"] >= 1

def test_v026_api_requires_token_and_ttl_audit_cleanup() -> None:
    from security import cleanup_sensitive_files, AUDIT_LOG_PATH, load_config
    client = TestClient(app)
    denied = client.post("/mask", json={"text": "Jan Kowalski"})
    assert denied.status_code == 401
    ok = post(client, "/mask", json={"text": "Jan Kowalski i ABC sp. z o.o."})
    assert ok.status_code == 200
    assert AUDIT_LOG_PATH.exists()
    log_text = AUDIT_LOG_PATH.read_text(encoding="utf-8")
    assert "Jan Kowalski" not in log_text
    assert "ABC sp. z o.o." not in log_text
    config = load_config()
    assert int(config["map_retention_days"]) >= 1
    assert "maps_removed" in cleanup_sensitive_files()


def test_v026_extended_legal_stoplists_and_uppercase_stopwords() -> None:
    text = (
        "Przedmiotem Umowy są Ogólnymi Warunkami oraz Informacjami Poufnymi. "
        "Kodeksem Cywilnym i Zarządem Klienta nie są danymi. BHP, OC, PPK, GUS, UODO i API pozostają jawne. "
        "ZXCV sp. z o.o., dalej jako ZXCV, ma zostać ukryta także jako ZXCV-u."
    )
    masked, replacements = make_replacements(text)
    for term in ["Przedmiotem Umowy", "Ogólnymi Warunkami", "Informacjami Poufnymi", "Kodeksem Cywilnym", "Zarządem Klienta", "BHP", "OC", "PPK", "GUS", "UODO", "API"]:
        assert term in masked, f"should remain visible: {term} -> {masked}"
    assert "ZXCV" not in masked
    assert "ZXCV-u" not in masked


def test_v019_placeholder_collision_is_avoided() -> None:
    text = "Klient [FIRMA_1] to ABC sp. z o.o."
    masked, replacements = make_replacements(text)
    assert "[FIRMA_1] to" in masked, masked
    assert "ABC sp. z o.o." not in masked
    generated = [r.placeholder for r in replacements if r.original == "ABC sp. z o.o."]
    assert generated and generated[0] != "[FIRMA_1]"
    restored = restore_text(masked, [r.__dict__ for r in replacements])
    assert restored == text


def test_v019_krs_context_wins_over_nip() -> None:
    text = "NIP: 5170383178, KRS: 0000897641"
    masked, replacements = make_replacements(text)
    assert any(r.category == "NIP" and r.original == "5170383178" for r in replacements)
    assert any(r.category == "KRS" and r.original == "0000897641" for r in replacements)
    assert "[KRS_1]" in masked


def test_v019_security_bypass_removed_and_health_minimal() -> None:
    import os
    client = TestClient(app)
    old = os.environ.get("CSM_DISABLE_AUTH")
    os.environ["CSM_DISABLE_AUTH"] = "1"
    try:
        denied = client.post("/mask", json={"text": "Jan Kowalski"})
        assert denied.status_code == 401
    finally:
        if old is None:
            os.environ.pop("CSM_DISABLE_AUTH", None)
        else:
            os.environ["CSM_DISABLE_AUTH"] = old
    health = client.get("/health")
    assert health.status_code == 200
    assert "config" not in health.json()


def test_v019_company_with_ampersand() -> None:
    text = "ABC & DEF sp. z o.o. zawarła umowę."
    masked, replacements = make_replacements(text)
    assert "ABC & DEF sp. z o.o." not in masked
    assert any(r.category == "COMPANY" and "ABC & DEF" in r.original for r in replacements)


def test_v019_license_pdf_and_backup_warning_files_exist() -> None:
    assert (ROOT / "LICENSE.txt").exists()
    assert (ROOT / "LICENSE.pdf").exists()
    assert (ROOT / "backups" / "WARNING.txt").exists()



def test_v021_person_aliases_dates_and_addresses() -> None:
    text = (
        "Jan Kowalski zawarł umowę. Jan przekazuje lokal. Pan Kowalski podpisze protokół. "
        "Z Anną Nowak omówiono sprawę. Anną kieruje dział. "
        "Umowę zawarto 12.03.2024 i od 1.04.2024 działa. "
        "Adres: ul. Słoneczna 12/3, 38-400 Krosno. Miasto Krosno samo zostaje. "
        "Drugi adres: ul. Słoneczna 12/3 w Krośnie. Miasto Krosno nadal zostaje. "
        "Trzeci adres: ul. Słoneczna 12/3 Krosno. "
        "Czwarty adres: ul. Słoneczna 12/3, Krosno. "
        "Piąty adres: ul. Słoneczna 12/3 w Krosno. "
        "Szósty adres: ul. Słoneczna 12/3 w Krośnie/Krosno. Miasto Krosno końcowo zostaje."
    )
    masked, replacements = make_replacements(text)
    assert "Jan Kowalski" not in masked
    assert "Jan przekazuje" not in masked
    assert "Pan Kowalski" not in masked
    assert "Anną kieruje" not in masked
    assert "12.03.2024" in masked
    assert "1.04.2024" in masked
    assert "ul. Słoneczna 12/3, 38-400 Krosno" not in masked
    assert "ul. Słoneczna 12/3 w Krośnie" not in masked
    assert "ul. Słoneczna 12/3 Krosno" not in masked
    assert "ul. Słoneczna 12/3, Krosno" not in masked
    assert "ul. Słoneczna 12/3 w Krosno" not in masked
    assert "ul. Słoneczna 12/3 w Krośnie/Krosno" not in masked
    assert "Miasto Krosno samo zostaje" in masked
    assert "Miasto Krosno nadal zostaje" in masked
    assert "Miasto Krosno końcowo zostaje" in masked
    import re as _re
    jan_families = {_re.match(r"\[(OSOBA_\d+)", r.placeholder).group(1) for r in replacements if r.original in {"Jan Kowalski", "Jan", "Kowalski"}}
    assert len(jan_families) == 1


def test_v021_uppercase_legal_heading_not_company_code() -> None:
    text = "UMOWA NAJMU LOKALU MIESZKALNEGO\nPrzedmiotem Umowy są Ogólne Warunki."
    masked, replacements = make_replacements(text)
    assert masked == text
    assert not replacements



def test_v025_taskpane_ux_and_revision_preservation_scenarios_are_present() -> None:
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")

    assert 'showTrackedChangesPreservationNotice' in js
    assert 'Kontynuuj i spłaszcz śledzone zmiany' not in html
    assert 'btnTrackContinue' not in html
    assert 'acceptAllChanges' not in js
    assert 'apiPost("/mask_docx_package"' not in js
    assert 'apiPost("/restore_docx_package"' not in js
    assert 'revisionPreservingMode' in js
    assert 'partsContainRevisionMarkup' in js
    assert 'requireTrackControl' in js
    assert 'Nie używam awaryjnego trybu tekstowego, żeby nie naruszyć historii zmian' in js

    assert 'function restoreReportNotice(report, replacementsPayload)' in js
    assert 'Brakujące dane (nie przywrócono)' in js
    assert 'restoreReportNoticeLevel(restoreReport, usedFallback)' in js
    assert 'Number(report.missing_total || 0) > 0) return "danger"' in js

    assert 'DATA_CLEAR_AFTER_RESTORE_SETTING_KEY' in js
    assert 'restoredDocumentClearWarningText' in js
    assert 'Dokument zawiera jawne dane po przywróceniu' in js
    assert 'Przygotuj aktywny dokument (tryb szybki)' in html
    assert 'Przywróć aktywny dokument' in html
    assert 'Przywróć dane i zakończ tryb Claude' not in html
    assert 'Nie pseudonimizuj ponownie' not in js
    assert 'white-space: pre-wrap' in html



def test_v028_taskpane_preserves_prepare_error_and_allows_unknown_tracking_for_normal_docs() -> None:
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "let operationSucceeded = false" in js
    assert "operationSucceeded = true" in js
    assert "if (operationSucceeded && !trackedChangesConsentPending)" in js
    assert "Do not refresh the panel after a failed prepare operation" in js
    assert "const trackingActuallyOn = Boolean(trackingRisk.hasTracking && !trackingRisk.unknown)" in js
    assert "const requireTrackControl = Boolean(partsHadRevisionMarkup || trackingActuallyOn)" in js
    # Normal documents must not be blocked only because the host cannot report changeTrackingMode.
    assert "revisionPreservingMode || trackingRisk.hasTracking || trackingRisk.unknown" in js
    assert 'apiPost("/mask_ooxml_parts"' in js
    assert 'apiPost("/mask_docx_package"' not in js
    assert "insertFileFromBase64(data.docx_base64" not in js
    assert "insertFileFromBase64" not in js
    assert "original_docx_package" not in js


def test_ooxml_parts_preserve_revision_markup_and_mask_deleted_text() -> None:
    client = TestClient(app)
    parts = {
        "body": (
            "<pkg:package xmlns:pkg='http://schemas.microsoft.com/office/2006/xmlPackage'>"
            "<pkg:part pkg:name='/word/document.xml'><pkg:xmlData>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p>"
            "<w:r><w:t>Poza zmianą Jan Kowalski mieszka przy ul. Słoneczna 12/3 w Krośnie.</w:t></w:r>"
            "<w:ins w:id='1' w:author='Anna Nowak'><w:r><w:t>Dodano Adam Nowicki PESEL 44051401359.</w:t></w:r></w:ins>"
            "<w:del w:id='2' w:author='Piotr Zieliński'><w:r><w:delText>Usunięto Ewa Malinowska NIP 8131689438.</w:delText></w:r></w:del>"
            "</w:p></w:body></w:document>"
            "</pkg:xmlData></pkg:part></pkg:package>"
        )
    }
    mask = post(client, "/mask_ooxml_parts", json={"parts": parts, "original_text": ""})
    assert mask.status_code == 200, mask.text
    data = mask.json()
    masked = data["parts"]["body"]
    assert "Jan Kowalski" not in masked
    assert "Adam Nowicki" not in masked
    assert "Ewa Malinowska" not in masked
    assert "44051401359" not in masked
    assert "8131689438" not in masked
    assert ":ins" in masked and ":del" in masked and ":delText" in masked
    assert "[OSOBA_" in masked
    assert "Anna Nowak" not in masked
    assert "Piotr Zieliński" not in masked

    restore = post(client, "/restore_ooxml_parts", json={"map_id": data["map_id"], "parts": data["parts"]})
    assert restore.status_code == 200, restore.text
    restored = restore.json()["parts"]["body"]
    report = restore.json()["restore_report"]
    assert "Jan Kowalski" in restored
    assert "Adam Nowicki" in restored
    assert "Ewa Malinowska" in restored
    assert "Anna Nowak" in restored
    assert "Piotr Zieliński" in restored
    assert ":ins" in restored and ":del" in restored and ":delText" in restored
    assert report["missing_total"] == 0, report
    assert report["leftover_total_after_restore"] == 0, report


def test_taskpane_uses_parts_for_tracked_changes_and_simple_two_button_ux() -> None:
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    assert 'button id="btnMain"' in html
    assert 'button id="btnRestore"' in html
    assert 'Przygotuj aktywny dokument (tryb szybki)' in html
    assert 'Przywróć aktywny dokument' in html
    assert 'Opcje awaryjne' in html
    assert 'apiPost("/mask_ooxml_parts"' in js
    assert 'apiPost("/restore_ooxml_parts"' in js
    assert 'apiPost("/mask_docx_package"' not in js
    assert 'apiPost("/restore_docx_package"' not in js
    assert 'modeKind = "parts"' in js
    assert 'partsContainRevisionMarkup(parts)' in js
    assert 'Tryb strukturalny ze śledzeniem zmian nie został zastosowany przez Word' in js
    assert 'maskVisibleTextByRange' in js
    assert 'modeKind = "range"' in js
    assert 'Przygotuj dokument dla Claude' not in html



def test_v031_ooxml_parts_do_not_create_cross_part_entities() -> None:
    client = TestClient(app)
    parts = {
        "body": (
            "<pkg:package xmlns:pkg='http://schemas.microsoft.com/office/2006/xmlPackage'>"
            "<pkg:part pkg:name='/word/document.xml'><pkg:xmlData>"
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p>"
            "<w:ins w:id='1' w:author='Anna Nowak'><w:r><w:t>Dodano Adam Nowicki.</w:t></w:r></w:ins>"
            "<w:del w:id='2' w:author='Piotr Zieliński'><w:r><w:delText>Usunięto Ewa Malinowska.</w:delText></w:r></w:del>"
            "</w:p></w:body></w:document>"
            "</pkg:xmlData></pkg:part></pkg:package>"
        ),
        "section0_header0": (
            "<w:hdr xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:p><w:r>"
            "<w:t>Kancelaria Testowa sp. z o.o., KRS 0000123456</w:t>"
            "</w:r></w:p></w:hdr>"
        ),
    }
    mask = post(client, "/mask_ooxml_parts", json={"parts": parts, "original_text": ""})
    assert mask.status_code == 200, mask.text
    data = mask.json()
    joined = "\n".join(data["parts"].values())
    assert "Kancelaria Testowa" not in joined, joined
    assert "0000123456" not in joined, joined
    assert "Anna Nowak" not in joined, joined
    assert "Piotr Zieliński" not in joined, joined

    restore = post(client, "/restore_ooxml_parts", json={"map_id": data["map_id"], "parts": data["parts"]})
    assert restore.status_code == 200, restore.text
    restored = "\n".join(restore.json()["parts"].values())
    assert "Kancelaria Testowa sp. z o.o." in restored
    assert "0000123456" in restored
    assert "Anna Nowak" in restored
    assert "Piotr Zieliński" in restored
    assert restore.json()["restore_report"]["missing_total"] == 0
    assert restore.json()["restore_report"]["leftover_total_after_restore"] == 0

def test_v027_docx_package_masks_overlapping_person_name_in_deleted_text() -> None:
    import base64, io, zipfile
    client = TestClient(app)
    files = {
        "word/document.xml": (
            "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body><w:p>"
            "<w:del w:id='2' w:author='Piotr Zieliński'><w:r>"
            "<w:delText>Usunięto Adam Nowicki PESEL 44051401359.</w:delText>"
            "</w:r></w:del>"
            "</w:p></w:body></w:document>"
        )
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    source_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    mask = post(client, "/mask_docx_package", json={"docx_base64": source_b64})
    assert mask.status_code == 200, mask.text
    data = mask.json()
    masked_raw = base64.b64decode(data["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(masked_raw), "r") as z:
        document = z.read("word/document.xml").decode("utf-8")
    assert "Adam Nowicki" not in document
    assert "Piotr Zieliński" not in document
    assert "44051401359" not in document
    assert "delText" in document
    assert "[OSOBA_" in document

    restore = post(client, "/restore_docx_package", json={"map_id": data["map_id"], "docx_base64": data["docx_base64"]})
    assert restore.status_code == 200, restore.text
    restored_raw = base64.b64decode(restore.json()["docx_base64"])
    with zipfile.ZipFile(io.BytesIO(restored_raw), "r") as z:
        restored_document = z.read("word/document.xml").decode("utf-8")
    report = restore.json()["restore_report"]
    assert "Adam Nowicki" in restored_document
    assert "Piotr Zieliński" in restored_document
    assert "44051401359" in restored_document
    assert "delText" in restored_document
    assert report["missing_total"] == 0, report
    assert report["leftover_total_after_restore"] == 0, report

def test_v033_no_cross_boundary_attribute_match_and_no_docx_replace() -> None:
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")
    assert "insertFileFromBase64" not in js
    assert "original_docx_package" not in js
    client = TestClient(app)
    body = ("<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:body>"
            "<w:p><w:del w:id='1' w:author='Anna Nowak'><w:r><w:delText>"
            "Usunięto adres: ul. Długa 5 w Warszawie."
            "</w:delText></w:r></w:del></w:p></w:body></w:document>")
    parts = {"body": body, "headers": "<w:hdr xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'><w:p><w:r><w:t>ABC sp. z o.o. KRS 0000123456</w:t></w:r></w:p></w:hdr>"}
    response = post(client, "/mask_ooxml_parts", json={"parts": parts, "original_text": ""})
    assert response.status_code == 200, response.text
    data = response.json()
    joined = "\n".join(data["parts"].values())
    assert "Anna Nowak" not in joined
    assert "Claude Safe Mode" not in joined
    assert "CSM" not in joined
    assert "ul. Długa" not in joined
    assert "ABC sp. z o.o." not in joined
    assert "0000123456" not in joined
    assert "author" in joined and "[OSOBA" in joined
    restore_response = post(client, "/restore_ooxml_parts", json={"map_id": data["map_id"], "parts": data["parts"]})
    assert restore_response.status_code == 200, restore_response.text
    restored = restore_response.json()
    restored_joined = "\n".join(restored["parts"].values())
    assert "Anna Nowak" in restored_joined
    assert "ul. Długa 5 w Warszawie" in restored_joined
    assert "ABC sp. z o.o." in restored_joined
    assert restored.get("restore_report", {}).get("missing_total", 0) == 0


def run_all() -> None:
    test_core_roundtrip()
    test_pesel_like_value_is_masked_even_if_checksum_fails()
    test_company_entities_are_masked_for_professional_secrecy()
    test_ooxml_replaces_values_split_across_runs()
    test_api_roundtrip()
    test_v022_api_rejects_oversized_text_payloads()
    test_v022_api_accepts_text_at_byte_limit()
    test_v024_docx_revision_report_detects_tracked_changes()
    test_api_ooxml_roundtrip()
    test_contract_context_aliases_and_inflections()
    test_ooxml_contract_alias_roundtrip()
    test_v011_professional_secrecy_checklist()
    test_v011_warnings_do_not_repeat_values()
    test_v012_identity_ledger_clusters_aliases()
    test_v012_engine_records_version_in_map()
    test_v021_ooxml_parts_headers_and_body_roundtrip()
    test_v021_placeholder_validation_detects_modified_placeholders()
    test_v022_docx_package_masks_comments_footnotes_and_metadata()
    test_v025_taskpane_ux_and_revision_preservation_scenarios_are_present()
    test_v021_map_is_wrapped_in_v2_envelope()
    test_v024_legal_headings_are_not_masked_but_party_codes_are()
    test_v024_docx_package_masks_comment_author_attributes()
    test_v025_settings_track_revisions_removed_and_legal_terms_keep_visible()
    test_v025_docx_package_preserves_revision_markup_and_masks_revision_text()
    test_v026_docx_package_restore_reports_missing_placeholders()
    test_v026_api_requires_token_and_ttl_audit_cleanup()
    test_v026_extended_legal_stoplists_and_uppercase_stopwords()
    test_v027_docx_package_masks_overlapping_person_name_in_deleted_text()
    test_v028_taskpane_preserves_prepare_error_and_allows_unknown_tracking_for_normal_docs()
    test_ooxml_parts_preserve_revision_markup_and_mask_deleted_text()
    test_taskpane_uses_parts_for_tracked_changes_and_simple_two_button_ux()
    test_v031_ooxml_parts_do_not_create_cross_part_entities()
    test_v033_no_cross_boundary_attribute_match_and_no_docx_replace()
    test_v019_placeholder_collision_is_avoided()
    test_v019_krs_context_wins_over_nip()
    test_v019_security_bypass_removed_and_health_minimal()
    test_v019_company_with_ampersand()
    test_v019_license_pdf_and_backup_warning_files_exist()
    test_v021_person_aliases_dates_and_addresses()
    test_v021_uppercase_legal_heading_not_company_code()


if __name__ == "__main__":
    run_all()
    print("OK: v1.0 backend TC preserve, pseudonimizacja terminology, REPERTORIUM/DECYZJA_ADM, CSM_MODE, no import side effects, DOCX bomb/XXE guard, error sanitizer, OOXML tracked-change path, restore safety tests passed")
