# CSM v0.6.1 — pseudonymization hardening report

Zakres zmiany:
- dodano residual PII quality gate dla wartości zapisanych w lokalnej mapie pseudonimizacji,
- kontrola nie ujawnia oryginalnych wartości w komunikatach; raportuje wyłącznie kategorie i liczby,
- bramka została użyta w ścieżkach tekstowych, OOXML, OOXML parts oraz DOCX v3/v4,
- dodano metadane retencji map (`retention_days`, `expires_at`),
- dodano testy regresyjne `tests/test_pseudonymization_quality_gate_hardening.py`,
- wersja paczki została oznaczona jako `0.6.1`.

Weryfikacja wykonana lokalnie:
- pytest chunk 1: 88 passed,
- pytest chunk 2: 203 passed,
- pytest chunk 3: 158 passed,
- pytest chunk 4: 98 passed, 3 skipped,
- `python tests/selftest.py`: passed,
- `npm run lint --silent`: passed,
- `npm run build --silent`: passed,
- render DOCX instrukcji: 2 strony PNG, bez błędów layoutu.

Pominięte testy:
- 3 testy realnego sidecara wymagają zmiennej `CSM_REVISION_SIDECAR_CMD` wskazującej skompilowany sidecar. W tym środowisku są pomijane zgodnie z warunkiem testu.
