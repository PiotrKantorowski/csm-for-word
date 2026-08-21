from redactor import make_replacements
from api import _build_anonymization_report, _build_restore_quality_report


def test_anonymization_report_contains_counts_risks_and_coverage():
    text = "Jan Nowacki, PESEL 77021500000, e-mail jan@example.com. Pozostaje ABCXYZ."
    masked, replacements = make_replacements(text)
    report = _build_anonymization_report(
        replacements,
        {"coverage": {"body": True, "comments": False, "metadata": 1}, "processed_parts": ["word/document.xml", "docProps/core.xml"], "skipped_parts": []},
        ["ostrzeżenie testowe"],
        None,
    )
    assert report["schema_version"] == "1.0"
    assert report["entities_unique"] == len(replacements)
    assert report["category_counts"]
    assert report["severity"] == "review"
    assert any("Przetworzono" in item for item in report["manual_review_items"])


def test_restore_quality_report_flags_leftover_placeholders():
    report = _build_restore_quality_report(
        {"restored_occurrences": 12, "leftover_total_after_restore": 1, "leftover_placeholders_after_restore": ["[OSOBA_99]"]},
        [],
        {"changed_from_prepare": True},
    )
    assert report["schema_version"] == "1.0"
    assert report["severity"] == "review"
    assert report["restored_occurrences"] == 12
    assert report["leftover_total_after_restore"] == 1
    assert any("pozostało" in item for item in report["manual_review_items"])
