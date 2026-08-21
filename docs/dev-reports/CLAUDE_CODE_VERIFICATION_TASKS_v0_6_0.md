# Zadania dla Claude Code / środowiska Windows przed finalnym CSM v0.6.1

## Cel

Potwierdzić te elementy, których nie da się sprawdzić w środowisku bez `dotnet` i bez Microsoft Word.

## Krok 1 — .NET SDK

```powershell
dotnet --info
```

Wymagane: .NET 8 SDK dostępny w PATH.

## Krok 2 — restore/build/test sidecara

```powershell
dotnet restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
dotnet build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release
```

Wymagane: wszystkie trzy komendy kończą się sukcesem.

## Krok 3 — Python -> realny program pomocniczy

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "dotnet run --project sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj --"
python -m pytest -q tests\test_revision_sidecar_integration.py
```

Wymagane: testy oznaczone wcześniej jako skipped mają przejść realnie.

## Krok 4 — workflow GitHub Actions

Sprawdzić, czy `.github/workflows/build-csm-installer.yml` przechodzi na `windows-latest`, w tym:

- npm lint/build,
- pytest,
- dotnet restore/build/test,
- Python integration z `CSM_REVISION_SIDECAR_CMD`,
- build instalatora.

## Krok 5 — Word/WebView runtime

Na Windows z Microsoft Word:

1. Zainstalować lub sideloadować aktualny manifest CSM.
2. Otworzyć dokument ze śledzeniem zmian.
3. Uruchomić przygotowanie `_CSM_anon`.
4. Sprawdzić panel: „Sprawdź zachowanie śledzenia zmian”.
5. Potwierdzić, że status mówi językiem użytkownika, nie technicznymi skrótami.
6. Wykonać restore po zmianach.
7. Potwierdzić, że historia zmian w Wordzie nie została spłaszczona.

## Wynik do zwrotu

Przekazać logi:

- `dotnet --info`,
- restore/build/test,
- wynik `tests/test_revision_sidecar_integration.py`,
- wynik workflow GitHub Actions albo lokalnego odpowiednika,
- screen/status z Worda,
- informację, czy installer `.exe` powstał.


## Dodatkowe warunki po audycie rc4

1. Nie wolno zmieniać `TargetFramework` z `net8.0` na `net11.0` tylko po to, żeby testy przeszły na lokalnej maszynie z preview SDK. Jeżeli brakuje .NET 8, zainstaluj .NET 8 SDK.
2. Przed buildem instalatora potwierdź, że `installer/CSM-Setup.iss` zawiera `LicenseFile={#SourceDir}\LICENSE.txt`.
3. Po uruchomieniu instalatora potwierdź ręcznie, że ekran licencji pojawia się przed rozpoczęciem instalacji i że odmowa akceptacji przerywa instalację.
4. Odbuduj `installer\output\CSM-Setup-v0.6.1.exe` dopiero po tej poprawce. Nie używaj starego EXE z paczki `final6(2).zip`.
5. Finalny ZIP nie może zawierać `__pycache__`, `.pyc`, `.pytest_cache`, `node_modules`, `.venv`, `bin` ani `obj`.
