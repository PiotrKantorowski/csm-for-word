# CSM v0.6.1 rc11 — research-driven install and reversible pseudonymization hardening

## Cel iteracji

Celem iteracji było przeprowadzenie audytu produktowego przed kolejnym przekazaniem do Claude Code:

1. zdiagnozować potencjalne problemy CSM, także te niewidoczne w pojedynczym teście na komputerze deweloperskim;
2. sprawdzić standardy i dobre praktyki pseudonimizacji oraz rozwiązań podobnych do CSM;
3. wdrożyć poprawki, które można bezpiecznie wykonać w tym środowisku;
4. przygotować paczkę źródłową do odbudowy instalatora EXE i testów Windows/Word.

## Źródła referencyjne sprawdzone poza GitHubem

### Pseudonimizacja i odwracalność

- RODO/GDPR: pseudonimizacja wymaga, aby danych nie można było przypisać do osoby bez „dodatkowych informacji”, a te dodatkowe informacje muszą być przechowywane osobno i zabezpieczone organizacyjnie oraz technicznie.
- ENISA, *Pseudonymisation techniques and best practices*: nacisk na modele atakującego, słownikowe zgadywanie, brute force, dobór technik i polityk pseudonimizacji.
- Microsoft Presidio Anonymizer: rozwiązanie referencyjne dla rozdzielenia wykrywania PII, operatorów anonimizacji i deanonymizacji; istotne jest także jawne zarządzanie mapowaniem i operatorami.

### Instalacja i Office Add-in

- Microsoft Learn, sideloading Office Add-ins: zaufany katalog sieciowy jest mechanizmem testowym dla Windows; manifest musi być dostępny w udziale, a użytkownik musi mieć skonfigurowany trusted catalog.
- Microsoft Learn, network share catalog: HTTPS jest zalecany, a certyfikat self-signed może działać tylko wtedy, gdy jest zaufany na lokalnej maszynie.
- pip docs: instalacja może korzystać z lokalnego katalogu wheels przez `--no-index --find-links`; sam cache pip nie gwarantuje pracy offline.

## Zdiagnozowane potencjalne problemy CSM

### 1. Instalator zależny od internetu i cache pip

W rc10 instalator był odporniejszy niż wcześniej, ale nadal instalował zależności Python głównie z PyPI. To oznacza ryzyko na komputerach z proxy, ograniczeniami firmowymi, problemami TLS albo brakiem internetu. Dokumentacja pip wskazuje, że cache ogranicza pobieranie, ale nie zastępuje lokalnego źródła pakietów. Dla przewidywalnej instalacji potrzebny jest wariant wheelhouse.

### 2. Emergency backup zawierał dodatkowe informacje w formie jawnej

`C:\CSM\backups\<map_id>` zapisywał m.in.:

- `original_visible_text.txt`,
- `original_ooxml.xml` / `original_ooxml_parts.json`,
- `original_docx_base64.txt`,
- `original_document.docx`.

To było wygodne dla recovery, ale z punktu widzenia pseudonimizacji jest ryzykowne: są to „dodatkowe informacje” pozwalające odwrócić pseudonimizację i powinny być zabezpieczone. W normalnym map store CSM używa DPAPI na Windows; emergency backup powinien iść tą samą drogą.

### 3. Zbyt szeroki detektor spółki/kontrahenta po etykiecie procesowej

Detektor nazw stron mógł w skrajnym przypadku potraktować zdanie `Powód okazał dowód osobisty ABA300000` jako nazwę kontrahenta. To powodowało, że poprawny numer dowodu osobistego był maskowany w ramach `[COMPANY_1]` zamiast `[IDCARD_PL_1]`. To był realny błąd klasyfikacji i potencjalnie utrudniał odwracalność oraz jakość mapy.

### 4. Komunikaty wydawnicze rc10 → rc11

Po dalszych zmianach paczka nie powinna już udawać rc10. Zmieniono aktywne etykiety na rc11, aby testerzy nie mylili badanej wersji.

## Wdrożone poprawki w rc11

### A. Zabezpieczenie emergency backupów

Zmieniono `server/redactor.py`:

- emergency backup zapisuje teraz jeden plik `backup_payload.csmmap`;
- payload używa tego samego mechanizmu envelope co mapa lokalna;
- na Windows payload jest chroniony przez DPAPI Current User;
- manifest backupu pozostaje jawny, ale zawiera tylko metadane: `map_id`, datę, hash, flagi obecności oryginalnych danych, metodę ochrony;
- stare jawne pliki backupu są usuwane przy zapisie nowego backupu;
- `load_install_backup()` nadal czyta stare backupy w trybie legacy, żeby nie odciąć użytkownika od odzysku dokumentów utworzonych starszą wersją.

### B. Obsługa lokalnego wheelhouse dla instalatora

Zmieniono `tools/setup-once.ps1`:

- dodano `$WheelhouseDir = server\wheelhouse`;
- jeśli w `server\wheelhouse` są pliki `.whl`, instalator używa `pip --no-index --find-links`;
- jeśli wheelhouse zawiera `pip-*.whl`, aktualizacja pip też idzie lokalnie;
- jeśli wheelhouse nie zawiera `pip-*.whl`, instalator pomija aktualizację pip i używa pip z `ensurepip`;
- jeśli wheelhouse nie istnieje lub jest pusty, zachowany jest dotychczasowy tryb online przez PyPI;
- dodano `server/wheelhouse/.keep`, żeby katalog był częścią paczki źródłowej i EXE.

### C. Poprawka klasyfikacji dowodu osobistego

Zmieniono `server/redactor.py`:

- detektor nazw stron/kontrahentów nie może już przechwytywać zwykłej frazy zaczynającej się od czasownika pisanego małą literą;
- dodatkowo odrzuca frazy zawierające `dowód osobisty`, `paszport`, `legitymuj...`;
- test `Powód okazał dowód osobisty ABA300000.` ponownie daje `[IDCARD_PL_1]`, nie `[COMPANY_1]`.

### D. Testy regresyjne rc11

Dodano `tests/test_rc11_install_privacy_hardening.py`, które sprawdza:

- backup odwracalnej pseudonimizacji nie zapisuje jawnych plików oryginału;
- `load_install_backup()` nadal potrafi odczytać chroniony payload;
- `setup-once.ps1` wspiera lokalny wheelhouse;
- przykłady `OLIMP LABORATORIES`, `Pustynia`, `Iwony Teresy Ustrzyckiej`, `Jan Mucha`, `Meble New Concept` przechodzą roundtrip: pseudonimizacja → przywrócenie → tekst identyczny.

## Testy wykonane lokalnie

Przeszły:

```text
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
python3 -m compileall -q server tests tools
```

Testy celowane:

```text
tests/test_rc11_install_privacy_hardening.py: 3 passed
wybrane testy instalatora, release hygiene, pseudonimizacji, restore, sidecar contract: 76 passed
wybrane testy person/company/context/current workflow/restore: 54 passed
revision sidecar group: 26 passed, 3 skipped
```

Pełny `pytest -q` został uruchomiony. Doszedł do ok. 76% bez błędów, po czym środowisko wykonawcze przerwało proces przez limit czasu. Testy sidecara realnego nadal są pomijane, jeśli `CSM_REVISION_SIDECAR_CMD` nie jest ustawiony.

## Niepotwierdzone w tym środowisku

- build nowego `CSM-Setup-v0.6.1.exe`,
- clean install na Windows,
- upgrade/repair po 0.5,
- instalacja z wheelhouse bez internetu,
- rzeczywisty Word/WebView,
- rzeczywisty sidecar .NET przez `CSM_REVISION_SIDECAR_CMD`.

## Decyzja

Ta paczka powinna być traktowana jako:

```text
CSM v0.6.1-rc11 SOURCE
```

Nie jest to finalne 0.6.1. Claude Code powinien odbudować EXE z tej dokładnej paczki, uzupełnić `server\wheelhouse` kołami dla Python 3.12 Windows x64 i wykonać testy z pliku `CLAUDE_CODE_REBUILD_AND_TEST_RC11.md`.
