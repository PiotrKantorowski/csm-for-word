# Claude Code — zakres testów i DoD dla CSM v0.6.1-rc4

## Cel

Zweryfikować paczkę po audycie `rc4`, w szczególności:

1. obowiązkową akceptację licencji w instalatorze Inno Setup,
2. powrót programu pomocniczego do .NET 8 LTS,
3. brak generowanych artefaktów w finalnym ZIP,
4. realne działanie programu pomocniczego .NET,
5. test w Microsoft Word/WebView.

## Ważne ograniczenie

Nie wolno zmieniać `TargetFramework` z `net8.0` na `net11.0` tylko dlatego, że lokalna maszyna ma zainstalowany .NET 11 preview. Jeżeli brakuje SDK, należy zainstalować .NET 8 SDK albo uruchomić test przez GitHub Actions z `actions/setup-dotnet@v5` i `dotnet-version: 8.0.x`.

## Zakres testów

### 1. Weryfikacja czystości paczki

W katalogu rozpakowanej paczki uruchom:

```powershell
Get-ChildItem -Recurse -Force | Where-Object {
  $_.Name -in @('__pycache__', '.pytest_cache', 'node_modules', '.venv', 'bin', 'obj') -or
  $_.Name -like '*.pyc'
} | Select-Object FullName
```

DoD:

- wynik jest pusty,
- finalny ZIP nie zawiera `__pycache__`, `.pyc`, `.pytest_cache`, `node_modules`, `.venv`, `bin`, `obj`.

### 2. Weryfikacja licencji w setupie

Sprawdź:

```powershell
Select-String -Path installer\CSM-Setup.iss -Pattern 'LicenseFile'
```

DoD:

- `installer/CSM-Setup.iss` zawiera `LicenseFile={#SourceDir}\LICENSE.txt`,
- plik `LICENSE.txt` istnieje w katalogu głównym paczki,
- po uruchomieniu instalatora użytkownik widzi ekran licencji,
- instalator nie pozwala przejść dalej bez akceptacji licencji,
- odmowa akceptacji przerywa instalację przed kopiowaniem plików i uruchamianiem skryptów.

### 3. Weryfikacja .NET 8

Uruchom:

```powershell
dotnet --info
Get-Content global.json
Get-Content sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
Get-Content sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj
```

DoD:

- dostępny jest .NET 8 SDK,
- `global.json` wskazuje SDK 8.0.100 z `rollForward: latestFeature`,
- oba projekty C# mają `<TargetFramework>net8.0</TargetFramework>`,
- nigdzie w aktywnych plikach projektu sidecara nie ma `net11.0`.

### 4. Build i testy .NET

Uruchom:

```powershell
dotnet restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
dotnet build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release
```

DoD:

- `restore` kończy się sukcesem,
- `build` kończy się sukcesem bez błędów,
- `dotnet test` kończy się sukcesem,
- nie ma zmiany TFM na `net11.0`.

### 5. Python -> realny program pomocniczy

Uruchom:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "dotnet run --project sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj --"
python -m pytest -q tests\test_revision_sidecar_integration.py
```

DoD:

- testy integracyjne realnego programu pomocniczego przechodzą,
- testy nie są pominięte,
- `tracked-replace` zwraca poprawny DOCX,
- wynikowy DOCX zawiera `w:ins` i `w:del`,
- działa treść główna, nagłówki, stopki, przypisy dolne, przypisy końcowe i komentarze.

### 6. Testy Node/Python

Uruchom:

```powershell
npm ci
npm run lint --silent
npm run build --silent
node --check addin\revision_bridge.js
node --check addin\taskpane.js
node --check addin\scripts\validate-static.js
python -m compileall -q server tests
python -m pytest -q
```

DoD:

- wszystkie testy przechodzą,
- brak failed,
- skipped są dopuszczalne tylko wtedy, gdy nie ustawiono realnego `CSM_REVISION_SIDECAR_CMD`; w teście finalnym z realnym programem pomocniczym skipped powinno być 0 dla testów sidecara.

### 7. Build instalatora

Uruchom:

```powershell
.\installer\build-csm-setup.ps1
```

DoD:

- powstaje nowy `installer\output\CSM-Setup-v0.6.1.exe`,
- EXE jest zbudowany po dodaniu `LicenseFile`, a nie pochodzi ze starej paczki,
- instalator pokazuje ekran licencji,
- odmowa licencji przerywa instalację,
- akceptacja licencji pozwala przejść dalej.

### 8. Test instalacji na czystym profilu Windows

DoD:

- instalacja kończy się bez błędów krytycznych,
- skrót CSM działa,
- lokalny backend startuje,
- panel Worda ładuje się,
- status mechanizmu śledzenia zmian jest czytelny dla prawnika,
- API nie pokazuje tokena, pełnej komendy ani pełnych ścieżek lokalnych.

### 9. Test Word/WebView

DoD:

- Word ładuje manifest CSM,
- panel działa w dokumencie testowym,
- przygotowanie dokumentu `_CSM_anon` działa,
- restore działa,
- śledzenie zmian nie jest spłaszczone,
- Word nie zgłasza naprawy uszkodzonego DOCX,
- użytkownik widzi komunikaty zrozumiałe dla prawnika, bez słów typu `sidecar`, `OOXML`, `capabilities`.

## Wynik, który trzeba zwrócić

Claude Code powinien zwrócić:

1. pełne logi `dotnet --info`, restore/build/test,
2. wynik `python -m pytest -q` i `tests\test_revision_sidecar_integration.py`,
3. informację, czy EXE został odbudowany po `LicenseFile`,
4. screenshot albo opis ekranu licencji instalatora,
5. screenshot albo opis testu Word/WebView,
6. SHA-256 finalnego ZIP i finalnego EXE,
7. potwierdzenie, że finalny ZIP nie zawiera cache/build artifacts.

## Warunek finalnego v0.6.1

Finalne `v0.6.1` można oznaczyć dopiero wtedy, gdy:

- .NET 8 build/test przejdą bez zmiany TFM,
- test realnego programu pomocniczego przejdzie bez skipped,
- instalator wymusi akceptację licencji,
- Word/WebView potwierdzi działanie w praktyce,
- finalny ZIP i EXE są czyste oraz aktualne.
