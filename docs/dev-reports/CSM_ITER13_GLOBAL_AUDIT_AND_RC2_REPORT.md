# CSM iteracja 13 — globalny audyt v0.6.1-rc2

Data: 2026-05-17

## 1. Co warto było zbadać

Audyt objął obszary, które są krytyczne dla lokalnego narzędzia Word Add-in dla prawników:

1. Zachowanie śledzenia zmian w Wordzie.
2. Trwałość mapy anonimizacji i restore.
3. Program pomocniczy .NET odpowiedzialny za operacje na strukturze dokumentu Word.
4. Bezpieczeństwo lokalnego API, w tym token i brak wycieku lokalnych ścieżek.
5. Odporność na nieprawidłowe pliki Word/ZIP.
6. Komunikaty dla użytkownika prawniczego.
7. Spójność dokumentacji wydania 0.6.1.
8. CI/CD i brak zależności od ręcznego zapewnienia testów sidecara.
9. Higiena paczki dystrybucyjnej.

## 2. Co sprawdzono w źródłach oficjalnych/GitHub

- Microsoft Word JavaScript API potwierdza model Word Add-in oparty o task pane i JavaScript działający w Wordzie.
- Microsoft Word API dokumentuje `changeTrackingMode`, czyli właściwy kierunek pracy z trybem śledzenia zmian.
- Microsoft Word API dokumentuje `customXmlParts`, co wspiera decyzję o trwałej mapie rewizyjnej w dokumencie.
- Microsoft dokumentuje zapisywanie ustawień add-inu w dokumencie oraz konieczność `saveAsync` dla trwałości ustawień.
- Clippit dokumentuje `OpenXmlRegex.Replace(..., trackRevisions, author)` jako mechanizm zamiany tekstu z obsługą śledzenia zmian.
- Clippit dokumentuje `RevisionProcessor` w namespace `Clippit.Word`, w tym akceptowanie/odrzucanie rewizji w wielu częściach dokumentu.
- GitHub Actions potwierdza aktualność użytych majorów `actions/checkout@v6` i `actions/upload-artifact@v7`.
- GitHub Actions ma aktualne `actions/setup-dotnet@v5`, które nadaje się do dodania obowiązkowego testu .NET 8.

## 3. Co znaleziono w paczce

### 3.1. Dobre elementy

- Wersje są zsynchronizowane na `0.6.1` w `VERSION.json`, `package.json`, `addin/package.json`, manifeście i instalatorze.
- Sidecar jest ustawiony na `net8.0`.
- Status mechanizmu zachowania śledzenia zmian jest chroniony tokenem.
- API redaguje lokalną komendę i ścieżkę programu pomocniczego.
- Backend waliduje wynik sidecara: sukces wymaga poprawnego pliku Word/ZIP z `word/document.xml`.
- Testy kontraktowe dla frontendu/backendu i statusu programu pomocniczego przechodzą.

### 3.2. Problemy wymagające poprawki

1. **Komunikaty dla prawników nadal miały elementy programistyczne.**
   W panelu nadal pojawiały się sformułowania typu `OOXML restore`, `Word Range API`, `DOCX/base64`, `tracked changes`.

2. **Release notes były niespójne.**
   Plik `RELEASE-NOTES-v0.6.1.txt` zawierał zlepek historycznych wpisów, w tym wzmianki o `v0.5`, `final2`, `final3`, `final5`, `final6`. To mogło mylić użytkownika i utrudniało odbiór jako 0.6.

3. **GitHub Actions nie sprawdzał jeszcze sidecara .NET.**
   Workflow uruchamiał Node/Python, ale nie wymuszał `dotnet restore`, `dotnet build`, `dotnet test` ani testu Python -> realny program pomocniczy.

4. **W tym środowisku nadal nie ma `dotnet`.**
   Lokalnie nie można było potwierdzić `dotnet restore/build/test`, więc ta część musi zostać wykonana przez GitHub Actions, Claude Code albo lokalnie na Windows/.NET 8.

## 4. Plan wdrożenia

1. Uprościć widoczne komunikaty w panelu i publiczne komunikaty API.
2. Wyczyścić release notes do jednej, aktualnej informacji o v0.6.1.
3. Dodać obowiązkowy etap .NET 8 do GitHub Actions.
4. Dodać testy zabezpieczające przed cofnięciem zmian językowych i release notes.
5. Uruchomić testy lokalne możliwe w tym środowisku.
6. Przygotować paczkę rc2 oraz osobne zadania dla Claude Code / środowiska Windows.

## 5. Co wdrożono

### 5.1. Komunikaty dla prawników

Zmieniono widoczne komunikaty m.in. z:

- `OOXML restore został wykonany...`
- `Word Range API...`
- `DOCX/base64...`
- `tracked changes...`

na prostsze komunikaty typu:

- `Przywracanie strukturalne zostało wykonane...`
- `kontrolowane dogranie widocznej treści...`
- `plik Word...`
- `śledzenie zmian...`

### 5.2. Release notes

Przepisano `RELEASE-NOTES-v0.6.1.txt` tak, aby:

- nie zawierał starych wpisów z poprzednich finali,
- jasno opisywał różnice względem 0.5,
- wskazywał warunki zamknięcia finalnego 0.6.1,
- był zrozumiały dla odbiorcy prawniczego.

### 5.3. GitHub Actions

Dodano do `.github/workflows/build-csm-installer.yml`:

```yaml
- uses: actions/setup-dotnet@v5
  with:
    dotnet-version: '8.0.x'

- run: dotnet restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
- run: dotnet build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release --no-restore
- run: dotnet test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release --no-restore
```

Dodano też test integracyjny Python z realnym programem pomocniczym przez `CSM_REVISION_SIDECAR_CMD`.

### 5.4. Testy zabezpieczające

Dodano/rozszerzono testy w `tests/test_release_hygiene.py`, które sprawdzają:

- obecność setup-dotnet i komend .NET w workflow,
- brak starych wpisów `final2/final3/final5/final6` w release notes,
- obecność prostszych komunikatów użytkownika,
- brak cofnięcia do technicznych komunikatów typu `OOXML restore` w panelu.

## 6. Testy wykonane lokalnie

Przeszły:

```text
npm run lint --silent: PASS
npm run build --silent: PASS
node --check addin/revision_bridge.js: PASS
node --check addin/taskpane.js: PASS
node --check addin/scripts/validate-static.js: PASS
python3 -m compileall -q server tests: PASS
pytest sidecar/status/frontend sync: 21 passed
pytest bridge/engine/token/UX/restore retry: 26 passed
pytest release/runtime/distribution/polish: 23 passed
pytest sidecar integration: 5 passed, 3 skipped
```

Pominięte 3 testy dotyczą realnego programu pomocniczego .NET i wymagają `CSM_REVISION_SIDECAR_CMD`.

## 7. Nadal niepotwierdzone lokalnie

```text
dotnet --info: command not found
dotnet restore: niewykonane lokalnie
dotnet build: niewykonane lokalnie
dotnet test: niewykonane lokalnie
Word/WebView runtime: niewykonane lokalnie
installer .exe: niewykonany lokalnie
```

## 8. Czy potrzebna jest pomoc Claude Code

Tak, ale tylko do warstwy środowiskowej:

1. Uruchomienia `.NET 8 SDK`.
2. `dotnet restore/build/test`.
3. Testu Python -> realny program pomocniczy.
4. Testu w Microsoft Word/WebView.
5. Opcjonalnie builda instalatora `.exe`.

Kodowo wykonano krok porządkujący rc2; bez powyższych testów nie należy deklarować finalnego 0.6.1 jako w pełni potwierdzonego produkcyjnie.

## 9. Rekomendacja

Ta paczka powinna być traktowana jako:

```text
CSM v0.6.1-rc2 — global audit polish + CI sidecar gate
```

Jeżeli GitHub Actions/Claude Code potwierdzi .NET i Word runtime, można ją oznaczyć jako finalne `0.6.1` bez kolejnej dużej iteracji funkcjonalnej.
