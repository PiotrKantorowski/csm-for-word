from __future__ import annotations

import io
import zipfile

from redactor import make_replacements, mask_ooxml_package_bytes


def _masked(text: str) -> tuple[str, list]:
    return make_replacements(text)


def test_masks_internet_and_technical_identifiers_without_masking_plain_terms():
    text = (
        "Domena: sklep-novus.pl, panel administracyjny panel.omnitex-it.pl. "
        "Adres IP: 192.168.10.15. Login administratora: admin.nowak. "
        "Token API: sk-proj-ABCDEFGHIJKLMNOPQRSTUV1234567890. "
        "Google Analytics ID: G-ABCD123456. Repozytorium GitHub: novus/shop-platform. "
        "Faktura nr FV/05/2026/001, ID transakcji TX-2026-05-001. "
        "Załącznik nr 4, § 2 ust. 3, termin 21 dni."
    )
    masked, replacements = _masked(text)
    originals = {r.original for r in replacements}
    cats = {r.category for r in replacements}
    assert "sklep-novus.pl" not in masked
    assert "panel.omnitex-it.pl" not in masked
    assert "192.168.10.15" not in masked
    assert "admin.nowak" not in masked
    assert "sk-proj-ABCDEFGHIJKLMNOPQRSTUV1234567890" not in masked
    assert "G-ABCD123456" not in masked
    assert "novus/shop-platform" not in masked
    assert "FV/05/2026/001" not in masked
    assert "TX-2026-05-001" not in masked
    assert {"DOMAIN", "IP_ADDRESS", "LOGIN", "SECRET", "ACCOUNT_ID", "REPOSITORY", "FINANCIAL_DOC_ID"} <= cats
    assert "Załącznik nr 4" in masked
    assert "§ 2 ust. 3" in masked
    assert "21 dni" in masked


def test_masks_pleading_third_party_roles_and_process_people():
    text = (
        "Pełnomocnik powoda radca prawny Anna Kowalska wnosi o przesłuchanie świadka Jana Malinowskiego. "
        "Biegły sądowy Marek Wiśniewski sporządził opinię, a notariusz Ewa Zielińska potwierdziła podpis. "
        "Piotr Nowak, komornik sądowy, prowadzi czynności."
    )
    masked, replacements = _masked(text)
    assert "Anna Kowalska" not in masked
    assert "Jana Malinowskiego" not in masked
    assert "Marek Wiśniewski" not in masked
    assert "Ewa Zielińska" not in masked
    assert "Piotr Nowak" not in masked
    assert any(r.category == "PERSON" for r in replacements)


def test_masks_word_metadata_comments_and_alt_text_attrs():
    # Minimal DOCX-like ZIP. The redactor processes content parts and docProps;
    # comments.xml carries author initials and text, and document.xml contains an
    # alt-text description attribute with a personal/company identifier.
    document_xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
                xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
      <w:body>
        <w:p><w:r><w:t>Kontakt techniczny: Jan Kowalski, login administratora: j.kowalski</w:t></w:r></w:p>
        <wp:docPr id="1" name="Screenshot Jan Kowalski" descr="Panel klienta KGL Commerce Solutions" />
      </w:body>
    </w:document>'''
    comments_xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:comment w:id="0" w:author="Anna Nowak" w:initials="AN">
        <w:p><w:r><w:t>Proszę sprawdzić z Michałem Zielińskim.</w:t></w:r></w:p>
      </w:comment>
    </w:comments>'''
    core_xml = '''<?xml version="1.0" encoding="UTF-8"?>
    <cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
      xmlns:dc="http://purl.org/dc/elements/1.1/">
      <dc:creator>Piotr Kantorowski</dc:creator>
      <dc:title>Umowa KGL Commerce Solutions</dc:title>
    </cp:coreProperties>'''
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/comments.xml", comments_xml)
        z.writestr("docProps/core.xml", core_xml)
    masked_bytes, replacements, report = mask_ooxml_package_bytes(buf.getvalue())
    with zipfile.ZipFile(io.BytesIO(masked_bytes), "r") as z:
        combined = "\n".join(z.read(n).decode("utf-8") for n in z.namelist())
    for leak in ["Jan Kowalski", "j.kowalski", "Anna Nowak", "Michałem Zielińskim", "Piotr Kantorowski", "KGL Commerce Solutions"]:
        assert leak not in combined
    assert "anonimowy" in combined or "[OSOBA_" in combined
    assert report["coverage"]["comments"] is True
    assert report["coverage"]["metadata"] >= 1
