# Raporty z rozwoju CSM

Ten katalog jest jawnym śladem tego, jak powstawał silnik pseudonimizacji: co dokładnie sprawdzono, co się nie udało i dlaczego podjęto konkretną decyzję. Pliki nie są dokumentacją użytkownika — instrukcja jest w [README](../../README.md) i w `Instrukcja_CSM_v1_6.docx`.

Nazwy plików mówią, czego dotyczy dany raport:

| Prefiks | Zawartość |
|---|---|
| `CSM_ITER*` | raporty z kolejnych iteracji rozwojowych, od audytu funkcji do wydania kandydata |
| `CSM_RC*` | audyty i poprawki konkretnych kandydatów do wydania, w tym raporty jakości pseudonimizacji |
| `CLAUDE_CODE_*` | zakresy testów, kryteria akceptacji i raporty weryfikacji na Windowsie |
| `CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_*` | reguły językowe dla polskiego dokumentu prawnego |
| `CSM_*AUDIT*` | audyty przekrojowe, w tym audyt gotowości komercyjnej |
| `CSM_SONNET5_*` | niezależna weryfikacja jakości i rozszerzony zestaw przypadków benchmarkowych |

Warto zajrzeć w pierwszej kolejności:

- [`CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md`](CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md) wraz z [addendum RC14](CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC14_ADDENDUM.md) — dlaczego `Pani Mucha` jest osobą, a `mucha` nie jest niczym;
- [`CSM_V16_HARD_FAMILIES_BENCHMARK_REPORT.md`](CSM_V16_HARD_FAMILIES_BENCHMARK_REPORT.md) — przypadki, których silnik świadomie jeszcze nie obsługuje, przypięte testem;
- [`CSM_RC32_REVERSIBILITY_AND_SURNAME_HARDENING_REPORT.md`](CSM_RC32_REVERSIBILITY_AND_SURNAME_HARDENING_REPORT.md) — odwracalność i nazwiska;
- [`CSM_COMMERCIALIZATION_AUDIT_2026-07-01.md`](CSM_COMMERCIALIZATION_AUDIT_2026-07-01.md) — audyt gotowości do wdrożenia u klientów.

Raporty opisują stan wiedzy z dnia, w którym powstały. Aktualny stan opisuje kod i pakiet testów, nie ten katalog.
