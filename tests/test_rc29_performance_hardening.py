import time

from redactor import (
    _find_literal_occurrences,
    _find_many_literal_occurrences,
    make_replacements,
    remove_overlaps,
)


def test_batched_literal_matching_matches_legacy_single_scans():
    text = (
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp.j. oraz "
        "Kantorowski, Głąb i Wspólnicy występują w sprawie. "
        "Jan Kowalski i Kowalski podpisali dokument."
    )
    requests = [
        ("COMPANY_ALIAS", "Kantorowski, Głąb i Wspólnicy"),
        ("COMPANY", "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp.j."),
        ("PERSON_ALIAS", "Kowalski"),
    ]
    batched = sorted(remove_overlaps(_find_many_literal_occurrences(text, requests)), key=lambda f: (f.start, f.end, f.category))
    legacy = []
    for category, value in requests:
        legacy.extend(_find_literal_occurrences(text, value, category))
    legacy = sorted(remove_overlaps(legacy), key=lambda f: (f.start, f.end, f.category))
    assert [(f.category, f.value, f.start, f.end) for f in batched] == [
        (f.category, f.value, f.start, f.end) for f in legacy
    ]


def test_long_repeated_contract_masks_kgl_without_superlinear_alias_scans():
    sample = (
        "Umowa pomiędzy Jan Kowalski, PESEL 80010112345, a "
        "Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp.j., "
        "KRS 0000123456, NIP 813-123-45-67. "
        "SO w Rzeszowie rozpoznaje sprawę. Müller GmbH i François Dupont. "
    )
    text = sample * 300
    start = time.perf_counter()
    masked, replacements = make_replacements(text)
    elapsed = time.perf_counter() - start
    assert "Głąb" not in masked
    assert "Kantorowski" not in masked
    assert "François Dupont" not in masked
    assert any(r.category == "COMPANY" for r in replacements)
    # Generous guard: catches accidental return to scanning the full document
    # once for every literal alias while avoiding fragile micro-benchmarking.
    assert elapsed < 15.0
