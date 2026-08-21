from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from redactor import make_replacements_with_controls, collect_uncertain_review_candidates


def test_uncertain_review_candidates_are_local_opt_in_not_auto_masked():
    text = "Nazwa robocza projektu: Alfa Zeta 2026. Umowę podpisano elektronicznie."
    masked, replacements = make_replacements_with_controls(text)

    assert "Alfa Zeta 2026" in masked
    assert all(r.original != "Alfa Zeta 2026" for r in replacements)

    candidates = collect_uncertain_review_candidates(text, replacements)
    assert any(c["value"] == "Alfa Zeta 2026" and c["category"] == "PROJECT" for c in candidates)


def test_selected_uncertain_candidate_can_be_added_to_manual_controls():
    text = "Nazwa robocza projektu: Alfa Zeta 2026. Umowę podpisano elektronicznie."
    masked, replacements = make_replacements_with_controls(
        text,
        {"always": [{"value": "Alfa Zeta 2026", "category": "PROJECT"}]},
    )

    assert "Alfa Zeta 2026" not in masked
    assert "[PROJEKT_1]" in masked or "[PROJECT_1]" in masked
    assert any(r.original == "Alfa Zeta 2026" for r in replacements)


def test_uncertain_review_suggests_reverse_address_and_descriptive_contractor():
    text = "Dostarczono do: 39-200 Dębica, Pustynia 84F. Główny wykonawca to Zielony Dach."
    masked, replacements = make_replacements_with_controls(text)
    candidates = collect_uncertain_review_candidates(text, replacements)
    values = {c["value"] for c in candidates}

    assert "39-200 Dębica, Pustynia 84F" in values
    assert "Zielony Dach" in values


def test_uncertain_review_ui_contract_exists():
    html = (ROOT / "addin" / "taskpane.html").read_text(encoding="utf-8")
    js = (ROOT / "addin" / "taskpane.js").read_text(encoding="utf-8")

    assert "uncertainReviewModal" in html
    assert "btnUncertainApply" in html
    assert "applySelectedUncertainReviewCandidates" in js
    assert "remaskWithManualControls" in js
    assert "uncertain_review_candidates" in js
