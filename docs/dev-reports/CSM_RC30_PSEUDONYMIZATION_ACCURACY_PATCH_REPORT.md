# CSM RC30 — pseudonymization accuracy patch

## Zakres

Patch realizuje etap 1 i 2 prac nad trafnością pseudonimizacji bez używania dokumentów klienta.

## Etap 1 — poprawione reguły

W `server/redactor.py` dodano lub wzmocniono:

- odmienne formy tytułów zawodowych i procesowych: `r.pr.`, `radca prawny`, `radcę prawnego`, `adw.`, `notariusz`, `komornik`, `mediator`, `tłumacz przysięgły`, `pełnomocnik`, `prokurent`;
- wykrywanie osób po konstrukcjach typu `reprezentowana przez r.pr. Annę Żuchowską-Czernię`;
- wykrywanie pełnomocników/substytutów z dodatkowymi określeniami, np. `pełnomocnika substytucyjnego r.pr. Macieja Grzebieniowskiego`;
- ostrożniejsze filtrowanie fałszywych trafień w tytułach dokumentów typu `UMOWA NAJMU LOKALU UŻYTKOWEGO` i w ogólnych nazwach projektów typu `System CRM ERP SaaS`;
- dodatkowe identyfikatory kontekstowe: numer silnika/nadwozia, `obrębie 0001`, numer CEIDG, login bez dwukropka, faktura w formie `faktury FV/...`, polisa OC, przesyłka/list polecony.

## Etap 2 — benchmark publiczny

Dodano benchmark:

- `tests/fixtures/public_legal_pseudonymization_benchmark.json` — 116 przypadków testowych;
- `tests/test_rc30_public_legal_pseudonymization_benchmark.py` — testy maskowania, zachowania tekstu i roundtrip;
- `tools/fetch_public_legal_benchmark_sources.py` — skrypt do pobrania publicznych źródeł referencyjnych, gdy środowisko ma dostęp do internetu.

Benchmark jest oparty na strukturach publicznych wzorów dokumentów i syntetycznych danych PII. Nie zawiera dokumentów klientów ani materiałów objętych tajemnicą zawodową.

## Źródła publicznych struktur dokumentów

- Gov.pl — wzór umowy sprzedaży samochodu;
- Gov.pl — wzory pełnomocnictw;
- Gov.pl — wzory umów najmu;
- Senat — wzór umowy najmu/podnajmu lokalu użytkowego;
- BIP Sądu Okręgowego w Warszawie — formularz odpowiedzi na pozew.

## Wyniki testów w kontenerze

- Celowane testy regresyjne i benchmark: `215 passed in 0.71s`.
- Pełny `pytest -q`: doszedł do ok. 90% wykonania, ale środowisko kontenera przekroczyło limit czasu. Nie odnotowano porażki przed timeoutem.

## Ważne ograniczenie

W kontenerze nie udało się pobrać plików binarnych z internetu przez `urllib` z powodu błędu DNS. Dlatego raw public-source files nie zostały dołączone. Dołączony skrypt pobierający pozwala odtworzyć źródła w środowisku z dostępem do sieci. Sam benchmark działa offline.
