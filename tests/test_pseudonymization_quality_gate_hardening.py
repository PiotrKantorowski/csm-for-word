from pathlib import Path

from redactor import (
    find_quality_gate_warnings,
    find_unmasked_original_residuals,
    load_map,
    make_replacements,
    save_map,
)


def test_quality_gate_flags_exact_originals_without_disclosing_values():
    text = "Jan Kowalski zawarł umowę z FENIX sp. z o.o."
    _masked, replacements = make_replacements(text)

    # Simulate a downstream/OXML edge case where one original value survived.
    unsafe_output = "[OSOBA_1] zawarł umowę z FENIX sp. z o.o."
    warnings = find_unmasked_original_residuals(unsafe_output, replacements)

    assert any("bramka residual PII" in w for w in warnings)
    joined = "\n".join(warnings)
    assert "FENIX" not in joined
    assert "Jan Kowalski" not in joined


def test_quality_gate_stays_quiet_after_successful_masking():
    text = "Jan Kowalski, PESEL 90010112345, e-mail jan.kowalski@example.com."
    masked, replacements = make_replacements(text)

    warnings = find_unmasked_original_residuals(masked, replacements)

    assert warnings == []
    assert "Jan Kowalski" not in masked
    assert "jan.kowalski@example.com" not in masked


def test_saved_map_contains_expiry_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("CSM_BASE_DIR", str(tmp_path))
    import redactor

    monkeypatch.setattr(redactor, "BASE_DIR", tmp_path)
    monkeypatch.setattr(redactor, "MAPS_DIR", tmp_path / "maps")
    import security

    monkeypatch.setattr(security, "BASE_DIR", tmp_path)
    monkeypatch.setattr(security, "MAPS_DIR", tmp_path / "maps")
    monkeypatch.setattr(security, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(security, "RUNTIME_DIR", tmp_path / "runtime")
    monkeypatch.setattr(security, "AUDIT_DIR", tmp_path / "audit")
    monkeypatch.setattr(redactor, "load_config", security.load_config)

    _masked, replacements = make_replacements("Anna Nowak, PESEL 90010112345")
    map_id = save_map(replacements)
    payload = load_map(map_id)

    assert payload["expires_at"]
    assert int(payload["retention_days"]) >= 1
