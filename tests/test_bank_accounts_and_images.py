from __future__ import annotations

import io
import zipfile

from api import _build_anonymization_report
from redactor import find_residual_risks, make_replacements
from tc_engine import mask_docx_preserving_tc, restore_docx_preserving_tc, restore_redacted_images_from_original


ORIGINAL_IMAGE = b"not-a-real-photo-but-sensitive-pixels"


def _minimal_docx_with_text_and_image(text: str = "Rachunek bankowy: 12 3456 7890 1234 5678 9012 3456") -> bytes:
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>'''.encode("utf-8")
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'></Types>")
        z.writestr("word/document.xml", document_xml)
        z.writestr("word/media/image1.png", ORIGINAL_IMAGE)
    return out.getvalue()


def _read_part(docx: bytes, name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(docx), "r") as z:
        return z.read(name)


def test_contextual_bank_account_is_masked_even_when_checksum_is_invalid():
    text = "Wynagrodzenie płatne na rachunek bankowy: 12 3456 7890 1234 5678 9012 3456."
    masked, replacements = make_replacements(text)

    assert "12 3456 7890 1234 5678 9012 3456" not in masked
    assert "[RACHUNEK_BANKOWY_1]" in masked
    assert any(r.category == "BANK_ACCOUNT" for r in replacements)


def test_bank_account_residual_risk_is_non_disclosing():
    risks = find_residual_risks("konto: 12 3456 7890 1234 5678 9012 3456")
    assert any("rachunek bankowy" in item for item in risks)
    assert not any("3456 7890" in item for item in risks)


def test_docx_images_are_redacted_in_anon_copy_and_reported():
    docx = _minimal_docx_with_text_and_image()
    masked_docx, replacements, report = mask_docx_preserving_tc(docx)

    assert _read_part(masked_docx, "word/media/image1.png") != ORIGINAL_IMAGE
    assert report["coverage"]["graphical_elements"]["images"] == 1
    assert report["coverage"]["graphical_elements"]["redacted_images"] == 1
    assert report["warnings"]
    assert any(r.category == "BANK_ACCOUNT" for r in replacements)


def test_restore_can_reinsert_original_images_from_local_original_package():
    original_docx = _minimal_docx_with_text_and_image()
    masked_docx, replacements, _report = mask_docx_preserving_tc(original_docx)
    restored_text_docx, restore_report = restore_docx_preserving_tc(masked_docx, replacements)
    restored_docx, image_report = restore_redacted_images_from_original(restored_text_docx, original_docx)

    assert _read_part(restored_docx, "word/media/image1.png") == ORIGINAL_IMAGE
    assert image_report["restored_images"] == 1
    assert restore_report["restored_occurrences"] >= 1


def test_v0423_report_has_bank_and_image_control_sections_without_raw_values():
    raw_account = "12 3456 7890 1234 5678 9012 3456"
    masked, replacements = make_replacements(f"konto do przelewu: {raw_account}")
    report = _build_anonymization_report(
        replacements,
        {
            "coverage": {
                "body": True,
                "graphical_elements": {"images": 1, "redacted_images": 1},
            },
            "processed_parts": ["word/document.xml"],
            "skipped_parts": [],
        },
        [],
        None,
    )

    rendered = str(report)
    assert report["schema_version"] == "1.0"
    assert report["control_sections"]["bank_accounts"]["found"] >= 1
    assert report["control_sections"]["bank_accounts"]["status"] == "masked"
    assert report["control_sections"]["graphical_elements"]["images_found"] == 1
    assert report["control_sections"]["graphical_elements"]["images_redacted"] == 1
    assert any("Rachunki bankowe" in item for item in report["manual_review_items"])
    assert any("Obrazy i elementy nietekstowe" in item for item in report["manual_review_items"])
    assert raw_account not in rendered
    assert "3456 7890" not in rendered
