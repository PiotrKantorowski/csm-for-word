# Claude Code — rebuild and verify CSM v0.6.1 rc11

## Cel

Doprowadzić CSM v0.6.1 rc11 do poziomu kandydata finalnego przez odbudowanie instalatora EXE i wykonanie testów środowiskowych Windows/Word, których nie można było wykonać w środowisku ChatGPT.

## Paczka wejściowa

Użyj dokładnie paczki:

```text
CSM_v0_6_1_rc11_research_install_reversibility_SOURCE.zip
```

Nie używaj żadnego wcześniejszego EXE. W szczególności nie używaj EXE z rc8/rc9/rc10, bo nie zawiera wszystkich poprawek rc11.

## Najważniejsze zmiany rc11 do potwierdzenia

1. Emergency backup odwracalnej pseudonimizacji nie zapisuje jawnych plików oryginału. Ma używać `backup_payload.csmmap` i manifestu.
2. Na Windows payload map/backup ma być chroniony przez DPAPI Current User.
3. Instalator obsługuje lokalny `server\wheelhouse` i może instalować zależności Python bez internetu przez `--no-index --find-links`.
4. Detektor nie może maskować frazy `Powód okazał dowód osobisty ABA300000` jako firmy; numer dowodu ma zostać `[IDCARD_PL_1]`.
5. Aktywne etykiety mają wskazywać rc11, a nie rc7/rc8/rc9/rc10 ani 0.5/final2/final6.

## Przygotowanie wheelhouse

Na Windows z Pythonem 3.12 x64 wykonaj z katalogu źródeł:

```powershell
py -3.12 -m pip download --only-binary=:all: --dest server\wheelhouse pip setuptools wheel -r server\requirements-runtime.txt
```

Następnie potwierdź, że w katalogu są koła co najmniej dla:

```text
pip
setuptools
wheel
fastapi
uvicorn
pydantic
python-dotenv
lxml
```

Wynik zapisz w raporcie. Instalator finalny powinien zawierać `server\wheelhouse\*.whl`, żeby instalacja nie zależała od internetu/PyPI na komputerze prawnika.

## Testy kodu przed buildem EXE

Z katalogu źródeł uruchom:

```powershell
npm run lint --silent
npm run build --silent
node --check addin\revision_bridge.js
node --check addin\taskpane.js
node --check addin\scripts\validate-static.js
python -m compileall -q server tests tools
python -m pytest -q tests\test_rc11_install_privacy_hardening.py tests\test_idcard_passport_checksum.py tests\test_installer_resilience_matrix.py tests\test_installer_runtime_resilience_rc7.py tests\test_release_hygiene.py tests\test_final_assets_cache_and_mapping_ux.py
python -m pytest -q tests\test_contextual_persons_and_roles.py tests\test_identity_document_person_company_context.py tests\test_pleadings_identifier_regression.py tests\test_legal_lexicon_contracts_pleadings.py tests\test_pseudonymization_extended_recommendations.py tests\test_current_workflow.py tests\test_restore_state_contract.py
```

DoD:

```text
zero failed tests
brak nieuzasadnionych skipped poza realnym sidecarem, jeśli sidecar nie został jeszcze zbudowany
```

## Build .NET sidecara

Wykonaj:

```powershell
dotnet --info
dotnet restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
dotnet build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release
```

DoD:

```text
TargetFramework: net8.0
zero failed tests
brak powrotu do net11.0
```

## Test Python -> realny sidecar

Po buildzie ustaw:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "dotnet run --project sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj --"
python -m pytest -q tests\test_revision_sidecar_integration.py
```

DoD:

```text
zero failed
zero skipped z powodu braku CSM_REVISION_SIDECAR_CMD
sidecar zwraca poprawny docx_base64 dla akcji wykonawczych
```

## Odbudowanie EXE

Zbuduj instalator Inno Setup z:

```text
installer\CSM-Setup.iss
```

Oczekiwany wynik:

```text
installer\output\CSM-Setup-v0.6.1.exe
```

DoD:

```text
EXE istnieje
EXE został zbudowany po wypełnieniu server\wheelhouse
EXE zawiera LicenseFile
EXE zawiera rc11, a nie rc10/rc9/rc8/rc7
```

## Clean install — świeży komputer/profil

Na maszynie/profilu bez CSM:

1. Uruchom EXE.
2. Potwierdź ekran licencji i brak drugiego ukrytego pytania o `AKCEPTUJE`.
3. Odłącz internet albo zablokuj PyPI i potwierdź, że instalacja zależności idzie z wheelhouse.
4. Sprawdź pliki diagnostyczne.

DoD:

```text
instalacja kończy się sukcesem
nie ma zawieszenia na końcu paska
C:\CSM\server\.venv\Scripts\python.exe istnieje
python -c "import fastapi, uvicorn, pydantic, lxml.etree" działa w .venv
backend działa na 127.0.0.1:8787
add-in HTTPS działa na https://localhost:3000
certyfikat localhost trusted=True
Word nie pokazuje żółtego błędu o zablokowanej zawartości dodatku
panel pokazuje v0.6.1 — rc11
```

## Upgrade/repair po CSM 0.5

Na profilu ze starym CSM 0.5/final2/final6:

1. Uruchom EXE rc11.
2. Potwierdź usunięcie lub nadpisanie starego stanu, cache i trusted catalog.
3. Potwierdź, że nie ma aktywnych tekstów/logów wskazujących v0.5/final2/final6 jako aktualną wersję.
4. Potwierdź, że uszkodzone `.venv` zostaje przebudowane.
5. Potwierdź, że certyfikat localhost zostaje naprawiony.

DoD:

```text
upgrade/repair kończy się sukcesem
backend /health zwraca version 0.6.1
Word ładuje panel rc11
stare cache bustery final2/final6 nie są ładowane przez Worda
```

## Test odwracalnej pseudonimizacji

W Wordzie przetestuj dokumenty zawierające:

```text
OLIMP LABORATORIES
Pustynia 84F, 39-200 Dębica
Jan Mucha
Renata Mucha
Pani Iwony Teresy Ustrzyckiej (PESEL: 90010112345)
Meble New Concept
Powód okazał dowód osobisty ABA300000
```

DoD:

```text
wartości jawne nie zostają w dokumencie po pseudonimizacji
ABA300000 jest [IDCARD_PL_1], nie częścią [COMPANY_1]
mapa pseudonimizacji pozwala przywrócić dokument
po restore tekst jest zgodny z oryginałem w zakresie wartości zastąpionych
C:\CSM\backups\<map_id> nie zawiera original_document.docx ani original_visible_text.txt
backup zawiera backup_payload.csmmap i backup_manifest.json
na Windows backup_manifest.json pokazuje protection_method = windows-dpapi-current-user
```

## Test Word / tracked changes

1. Włącz dokument z aktywnym śledzeniem zmian.
2. Wykonaj pseudonimizację.
3. Wprowadź zmianę w Claude/Word.
4. Wykonaj restore.
5. Zweryfikuj, że Word pokazuje zmiany jako śledzone, a nie jako zwykłe podstawienie tekstu.

DoD:

```text
DOCX otwiera się bez naprawy
w document.xml są poprawne w:ins / w:del tam, gdzie oczekiwane
Word nie traci komentarzy/nagłówków/stopek/przypisów
```

## Raport końcowy Claude Code

W paczce zwrotnej dodaj plik:

```text
CLAUDE_CODE_RC11_WINDOWS_VERIFICATION_REPORT.md
```

Raport ma zawierać:

```text
SHA-256 paczki wejściowej
SHA-256 paczki wyjściowej
SHA-256 EXE
lista wykonanych komend
wyniki testów
informacja, czy wheelhouse działał offline
informacja, czy clean install przeszedł
informacja, czy upgrade/repair po 0.5 przeszedł
informacja, czy Word/WebView przeszedł
informacja, czy pseudonimizacja i restore przeszły
lista rzeczy niepotwierdzonych
```

## Nazwa paczki zwrotnej

Jeżeli wszystko przejdzie:

```text
CSM_v0_6_1_rc11_WINDOWS_VERIFIED.zip
```

Jeżeli cokolwiek nie przejdzie:

```text
CSM_v0_6_1_rc11_WINDOWS_TESTED_WITH_FAILURES.zip
```

Nie nazywaj paczki `FINAL`, jeśli którykolwiek element DoD nie przeszedł.
