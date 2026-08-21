# Claude Code — zakres testów i DoD dla CSM v0.6.1-rc5

## Cel

Potwierdzić, że `CSM_v0_6_1_rc5_post_claude_audit_clean.zip` może zostać oznaczony jako finalne `v0.6.1`.

Ta paczka została oczyszczona po audycie ChatGPT. Nie zmieniaj docelowego TFM z `net8.0` na `net11.0`. Jeżeli lokalna maszyna ma tylko .NET 11 preview, doinstaluj .NET 8 SDK albo uruchom test przez GitHub Actions z `actions/setup-dotnet@v5` i `dotnet-version: 8.0.x`.

## 1. Weryfikacja źródła

Uruchom w katalogu głównym paczki:

```powershell
Get-Content .\global.json
Select-String -Path .\sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -Pattern '<TargetFramework>net8.0</TargetFramework>'
Select-String -Path .\sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -Pattern '<TargetFramework>net8.0</TargetFramework>'
Select-String -Path .\installer\CSM-Setup.iss -Pattern 'LicenseFile=\{#SourceDir\}\\LICENSE.txt'
```

### DoD

- `global.json` zawiera `version: 8.0.100` i `rollForward: latestFeature`.
- Oba projekty `.csproj` mają `net8.0`.
- W aktywnych `.csproj` nie ma `net11.0`.
- `installer/CSM-Setup.iss` zawiera `LicenseFile={#SourceDir}\LICENSE.txt` przed sekcją `[Files]`.

## 2. Higiena paczki

```powershell
Get-ChildItem -Recurse -Force | Where-Object {
  $_.Name -in @('__pycache__', '.pytest_cache', 'node_modules', 'bin', 'obj') -or $_.Name -like '*.pyc'
} | Select-Object FullName
```

### DoD

- Brak `node_modules`.
- Brak `bin` i `obj` poza ewentualnymi artefaktami tworzonymi dopiero w trakcie lokalnego buildu.
- Brak `__pycache__`, `.pytest_cache`, `.pyc`.
- Jeżeli testy/builde tworzą te katalogi, wyczyść je przed finalnym ZIP-em.

## 3. Frontend / Node

```powershell
npm ci
npm run lint --silent
npm run build --silent
node --check addin\revision_bridge.js
node --check addin\taskpane.js
node --check addin\scripts\validate-static.js
```

### DoD

- Wszystkie komendy kończą się kodem `0`.
- `install-guide.html` zawiera `CSM-Setup-v0.6.1.exe`.
- Nie ma komunikatów technicznych niezrozumiałych dla prawnika w widocznym UI.

## 4. Backend Python

```powershell
python -m pip install -r server\requirements.txt
python -m compileall -q server tests
python -m pytest -q
```

### DoD

- `python -m pytest -q` bez realnego sidecara może mieć tylko testy pominięte dotyczące realnego `CSM_REVISION_SIDECAR_CMD`.
- Brak testów nieudanych.
- Endpointy wymagające tokena nadal zwracają `401` bez tokena.
- Status programu pomocniczego nie ujawnia pełnej komendy, tokena ani ścieżki lokalnej.

## 5. .NET sidecar — obowiązkowo na .NET 8

```powershell
dotnet --info
dotnet restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
dotnet build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release
```

### DoD

- Użyty SDK jest z linii `.NET 8` albo build jest jawnie skonfigurowany przez `global.json` i `actions/setup-dotnet@v5` na `8.0.x`.
- `dotnet build` kończy się bez błędów.
- `dotnet test` kończy się bez błędów i bez pominiętych testów sidecara.
- Nie wolno zmieniać TFM na `net11.0` tylko dlatego, że lokalnie dostępny jest preview SDK.

## 6. Python → realny sidecar

Po buildzie:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "dotnet run --project sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj --"
python -m pytest -q tests\test_revision_sidecar_integration.py
```

### DoD

- 0 failed.
- 0 skipped.
- `tracked-replace` zwraca poprawny DOCX.
- Wynikowy DOCX zawiera śledzone zmiany `w:ins` i `w:del`.
- Mechanizm działa dla treści głównej, nagłówków, stopek, przypisów i komentarzy.

## 7. Instalator Inno Setup

Odbuduj instalator:

```powershell
.\installer\build-csm-setup.ps1
```

Następnie uruchom `installer\output\CSM-Setup-v0.6.1.exe` na czystym profilu testowym Windows.

### DoD

- Instalator pokazuje ekran licencji.
- Instalator nie pozwala przejść dalej bez akceptacji licencji.
- Po akceptacji licencji instalacja kończy się sukcesem.
- Powstają skróty: `CSM – uruchom`, `CSM – zatrzymaj`, `CSM – diagnoza`.
- Word Trusted Catalog / zaufany katalog dodatku jest ustawiony.
- `install-guide.html` otwiera się po instalacji i pokazuje zrozumiałe instrukcje.

## 8. Test Microsoft Word / WebView

Na komputerze z Microsoft Word:

1. Zainstaluj CSM z EXE.
2. Uruchom Word.
3. Sprawdź, czy dodatek CSM jest widoczny.
4. Otwórz dokument testowy z danymi osobowymi w treści, nagłówku, stopce, przypisie i komentarzu.
5. Wykonaj anonimizację.
6. Wykonaj przywrócenie wersji jawnej.
7. Sprawdź śledzenie zmian w UI Worda.

### DoD

- Word nie wymaga naprawy dokumentu.
- Dane są przywracane jako śledzone zmiany.
- Prawnik widzi w Wordzie normalne śledzenie zmian, nie techniczny zapis XML.
- UI CSM nie pokazuje żargonu typu `sidecar`, `OOXML`, `base64`, `capabilities` w ścieżce użytkownika.

## 9. Finalny ZIP

Po wszystkich testach przygotuj finalny ZIP bez artefaktów roboczych.

### DoD finalnego ZIP-a

- `unzip -t`: OK.
- Brak `node_modules`, `bin`, `obj`, `__pycache__`, `.pytest_cache`, `.pyc`.
- Jeżeli ZIP zawiera `installer/output/CSM-Setup-v0.6.1.exe`, to EXE musi być odbudowany po dodaniu `LicenseFile` i po pozytywnym teście ekranu licencji.
- Raport końcowy zawiera SHA-256 ZIP-a i SHA-256 EXE.

## Werdykt wymagany od Claude Code

Raport końcowy ma zakończyć się jednym z dwóch werdyktów:

1. `READY FOR v0.6.1 FINAL` — jeżeli wszystkie punkty DoD są spełnione.
2. `NOT READY` — jeżeli którykolwiek punkt DoD nie przeszedł, wraz z listą blokujących problemów.
