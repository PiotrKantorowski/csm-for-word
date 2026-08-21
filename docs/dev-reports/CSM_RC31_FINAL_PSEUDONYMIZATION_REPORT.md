# CSM RC31 — final pseudonymization accuracy package

## Cel

RC31 finalizuje etap 1 i 2 prac nad poprawą trafności pseudonimizacji bez używania dokumentów klienta ani materiałów objętych tajemnicą zawodową.

## Co zawiera paczka

### 1. Poprawki silnika pseudonimizacji

Wzmocniono reguły w `server/redactor.py`, w szczególności dla:

- tytułów zawodowych i procesowych: `r.pr.`, `radca prawny`, `radcę prawnego`, `adw.`, `notariusz`, `komornik`, `mediator`, `tłumacz przysięgły`, `pełnomocnik`, `pełnomocnik substytucyjny`, `prokurent`;
- konstrukcji typu `reprezentowana przez r.pr. Annę Żuchowską-Czernię`;
- nazwisk dwuczłonowych i imion/nazwisk w odmianie;
- danych JDG i danych reprezentacji;
- dodatkowych identyfikatorów kontekstowych: numer silnika, numer nadwozia/VIN, numer CEIDG, obręb ewidencyjny, faktura `FV/...`, polisa OC, list/przesyłka polecona, login;
- ograniczenia fałszywych trafień w nagłówkach dokumentów i neutralnych frazach biznesowych.

### 2. Publiczny benchmark prawniczy

Dodano:

- `tests/fixtures/public_legal_pseudonymization_benchmark.json` — 116 przypadków testowych;
- `tests/test_rc30_public_legal_pseudonymization_benchmark.py` — testy maskowania, zachowania tekstu i roundtrip;
- `tests/test_rc31_public_source_manifest.py` — test integralności pobranych publicznych źródeł;
- `tests/fixtures/public_sources_raw/` — publiczne pliki źródłowe pobrane do paczki;
- `tests/fixtures/public_sources_raw/manifest.json` — SHA-256, rozmiary i URL-e źródeł;
- `tools/fetch_public_legal_benchmark_sources.py` — skrypt pobrania lub weryfikacji źródeł.

Benchmark nie zawiera dokumentów klienta. Dane identyfikujące użyte w przypadkach testowych są syntetyczne.

## Publiczne źródła wykorzystane do struktury benchmarku

- Gov.pl — wzór umowy sprzedaży samochodu;
- Gov.pl — alternatywny wzór/załącznik umowy sprzedaży pojazdu;
- Gov.pl — wzór pełnomocnictwa;
- Gov.pl — wzór umowy najmu lokalu użytkowego;
- Senat — wzór umowy najmu/podnajmu lokalu użytkowego;
- BIP Sądu Okręgowego w Warszawie — formularz odpowiedzi na pozew.

## Wyniki testów

### Testy Python / pytest

Pełny zestaw testów uruchomiono segmentami, ponieważ jednorazowe uruchomienie całego `pytest -q` przekracza limit czasu kontenera. Wynik łączny segmentów:

- `718 passed`
- `3 skipped`
- `0 failed`

Segmenty:

- segment 1: `120 passed in 4.19s`
- segment 2: `208 passed in 8.18s`
- segment 3: `290 passed in 10.44s`
- segment 4a: `30 passed, 3 skipped in 20.90s`
- segment 4b: `36 passed in 10.19s`
- segment 4c: `34 passed in 1.67s`

Dodatkowa weryfikacja po poprawie skryptu źródłowego:

- `tests/test_rc31_public_source_manifest.py`: `2 passed in 0.21s`

### Testy dodatku Word / static validation

Uruchomiono:

```bash
cd addin
node scripts/validate-static.js --build
```

Wynik:

```text
CSM build validation passed for v1.4.
```

### Testy .NET sidecar

Nie zostały uruchomione w tym kontenerze, ponieważ środowisko nie ma zainstalowanego `dotnet`.

W pytest pominięte zostały 3 testy realnego sidecara oznaczone jako wymagające `CSM_REVISION_SIDECAR_CMD` i skompilowanego sidecara. Testy fake-sidecar oraz kontrakty API przeszły.

## Ograniczenia

1. Paczka została zweryfikowana w kontenerze Linux, a nie w docelowym środowisku Windows + Word.
2. Nie uruchomiono realnych testów .NET sidecara z powodu braku `dotnet` w kontenerze.
3. „Idealna” trafność pseudonimizacji w sensie 100% nie jest możliwa do uczciwego zagwarantowania dla każdego dokumentu prawniczego. RC31 istotnie zwiększa pokrycie typowych i trudniejszych polskich przypadków, ale nadal zalecany jest przegląd dokumentu po pseudonimizacji przy danych szczególnie wrażliwych lub sprawach objętych tajemnicą zawodową.

## Rekomendowany następny krok

Przed użyciem produkcyjnym na Windows zalecane jest uruchomienie:

```bash
python -m pytest -q
cd addin && node scripts/validate-static.js --build
```

oraz test ręczny w Wordzie na publicznych/syntetycznych dokumentach: umowa, pełnomocnictwo, pismo procesowe, najem, JDG, nieruchomość.
