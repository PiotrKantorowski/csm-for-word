# Claude Code — wytyczne dla CSM v0.6.1 rc13

## Cel

Doprowadzić CSM v0.6.1 do kandydata finalnego przez:

1. odbudowanie instalatora EXE z paczki `rc13 source`,
2. testy instalacji na czystym profilu i po starej wersji 0.5,
3. wdrożenie i walidację reguł z `CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md`,
4. potwierdzenie odwracalnej pseudonimizacji w rzeczywistych dokumentach Word.

## Wejście

Pracuj wyłącznie na paczce:

```text
CSM_v0_6_1_rc13_polish_pseudonymization_install_SOURCE.zip
```

Nie używaj żadnego starszego EXE. EXE z rc12 jest nieaktualny, bo rc13 usuwa backupi z paczki, poprawia aktywne etykiety instalatora oraz dodaje reguły pseudonimizacji polskiej.

## Zasady bezwzględne

- Nie zmieniaj `net8.0` na `net9`, `net10` ani `net11`.
- Nie usuwaj `LicenseFile` z instalatora.
- Nie przywracaj jawnych backupów typu `original_visible_text.txt`.
- Nie pakuj `backups/<map_id>`, `sessions`, `__pycache__`, `.pyc`, `.pytest_cache`, `bin`, `obj`, `node_modules` do źródłowego ZIP-a.
- Nie oznaczaj wyniku jako finalne `0.6.1`, jeśli Word/WebView, GUI installer i upgrade po 0.5 nie są potwierdzone ręcznie.

## 1. Walidacja źródła

Z katalogu źródłowego uruchom:

```powershell
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
py -3.12 -m compileall -q server tests tools
py -3.12 -m pytest -q tests/test_rc13_polish_pseudonymization_rules.py tests/test_pseudonymization_extended_recommendations.py tests/test_legal_lexicon_contracts_pleadings.py tests/test_rc11_install_privacy_hardening.py tests/test_installer_resilience_matrix.py tests/test_release_hygiene.py tests/test_final_assets_cache_and_mapping_ux.py tests/test_installer_runtime_resilience_rc7.py
```

DoD: zero failed. Skipped są dopuszczalne tylko dla testów, które wprost wymagają nieskompilowanego sidecara przed buildem.

## 2. .NET sidecar

```powershell
dotnet --info
dotnet restore sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj
dotnet build sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj -c Release --no-restore
dotnet restore sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj
dotnet test sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj -c Release --no-restore
```

Następnie test Python przez skompilowany EXE:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = (Resolve-Path "sidecar/CSM.RevisionSidecar/bin/Release/net8.0/CSM.RevisionSidecar.exe").Path
py -3.12 -m pytest -q tests/test_revision_sidecar_integration.py
```

DoD: `dotnet test` bez failed/skipped; integracja sidecara 8/8 PASS.

## 3. Wheelhouse i instalacja offline

Sprawdź, że `server/wheelhouse` zawiera komplet wheeli dla Python 3.12 / Windows x64. Jeżeli trzeba, odbuduj wheelhouse:

```powershell
py -3.12 -m pip download -r server/requirements-runtime.txt --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp --abi cp312 --dest server/wheelhouse
```

DoD: `setup-once.ps1` podczas instalacji używa lokalnego wheelhouse (`--no-index --find-links`) i nie potrzebuje PyPI.

## 4. Build instalatora

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/CSM-Setup.iss
Get-FileHash installer/output/CSM-Setup-v0.6.1.exe -Algorithm SHA256
```

DoD:

- EXE istnieje,
- zawiera `LICENSE.txt`,
- build tag w plikach wskazuje `rc13`,
- instalator nie pokazuje aktywnych tekstów `rc11`, `rc12`, `0.5.0`, `final2`, `final6`.

## 5. GUI installer — test ręczny

Na czystym profilu Windows:

1. Uruchom `CSM-Setup-v0.6.1.exe` bez `/VERYSILENT`.
2. Sprawdź ekran licencji: bez akceptacji nie wolno przejść dalej.
3. Zaakceptuj licencję.
4. Obserwuj końcówkę instalacji.
5. Instalator nie może wisieć przy końcu paska.
6. Po zakończeniu sprawdź:
   - `%TEMP%\CSM-install.log`,
   - `%TEMP%\CSM-setup-once.log`,
   - `C:\CSM\server\.venv\Scripts\python.exe`,
   - `C:\CSM\server\wheelhouse`,
   - `https://localhost:3000/taskpane.html`,
   - `http://127.0.0.1:8787/health`.

DoD: instalator kończy się jednoznacznym komunikatem sukcesu, bez wiszenia i bez błędu pip cache.

## 6. Upgrade/repair po CSM 0.5

Na profilu ze starą instalacją CSM 0.5/final2/final6:

1. Nie czyść ręcznie `C:\CSM` przed testem.
2. Uruchom EXE rc13.
3. Sprawdź, że stare cache Worda są czyszczone.
4. Sprawdź, że uszkodzone `.venv` jest wykryte i odbudowane.
5. Sprawdź, że stary certyfikat/brak certyfikatu jest naprawiony.
6. Sprawdź, że aktywny panel pokazuje rc13, nie 0.5/final.

DoD:

- backend `/health` zwraca `version: 0.6.1`,
- add-in HTTPS działa,
- certyfikat `localhost` ma `trusted=True`,
- Word nie pokazuje blokady dodatku,
- nie zostają aktywne cache-bustery `final2/final6`.

## 7. Word/WebView

W Microsoft Word:

1. Otwórz dodatek CSM.
2. Sprawdź brak komunikatu o zablokowanym dodatku.
3. Sprawdź panel i status techniczny.
4. Uruchom pseudonimizację przykładowego pozwu, umowy i aktu notarialnego.
5. Uruchom restore.
6. Sprawdź, że przywrócony dokument odpowiada treści oryginalnej.
7. Sprawdź zachowanie śledzenia zmian, jeżeli sidecar jest dostępny.

DoD: Word ładuje panel, pseudonimizacja i restore przechodzą na realnych DOCX.

## 8. Reguły pseudonimizacji polskiej

Wdrożenie i testy prowadź według:

```text
CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md
```

Minimalne przypadki do potwierdzenia:

```text
Powód Jan Nowak, PESEL 90010112345
Pozwany Anna Kowalska
na rzecz Pani Iwony Teresy Ustrzyckiej (PESEL: 90010112345)
Jan Mucha / Renata Mucha / Anna Pustynia
zamieszkały w Pustyni
Pustynia 84F, 39-200 Dębica
Powód: OLIMP LABORATORIES z siedzibą w Pustyni, NIP 1234567890
Klient: Meble New Concept
Rachunek bankowy Jana Nowaka: PL 12 3456 7890 1234 5678 9012 3456
Faktura VAT numer: 1234567890
Sąd Rejonowy dla Warszawy-Mokotowa w Warszawie, I C 123/25
```

Każdy przypadek ma mieć:

- `must_mask`,
- `must_keep`,
- kategorię placeholdera,
- test roundtrip.

## 9. Raport końcowy Claude Code

Wygeneruj raport:

```text
CLAUDE_CODE_RC13_FINALIZATION_REPORT.md
```

Raport musi zawierać:

- SHA-256 wejściowego ZIP-a,
- SHA-256 EXE,
- wersje Python/Node/npm/.NET/Inno Setup,
- wynik lint/build/node/compileall/pytest,
- wynik `dotnet restore/build/test`,
- wynik sidecar integration przez EXE,
- wynik GUI install,
- wynik upgrade/repair po 0.5,
- wynik Word/WebView,
- wynik pseudonimizacji i restore na dokumentach prawniczych,
- listę rzeczy nadal niepotwierdzonych.

## 10. Nazwa paczki zwrotnej

Jeżeli wszystkie testy przejdą:

```text
CSM_v0_6_1_rc13_WINDOWS_VERIFIED.zip
```

Jeżeli którekolwiek z GUI/Word/upgrade nie przejdzie:

```text
CSM_v0_6_1_rc13_WINDOWS_TESTED_WITH_FAILURES.zip
```

Nie używaj nazwy `FINAL`, dopóki wszystkie blokery finalnego 0.6 nie są zamknięte.
