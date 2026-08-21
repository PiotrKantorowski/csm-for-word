# CSM — audyt odbiorczy paczki po Claude Code

Data: 2026-05-17

## Zakres

Audyt wykonano zgodnie z handoffem `CSM_THREAD_HANDOFF_FULL_FOR_NEW_CHAT.md`: ZIP, higiena paczki, raporty MD, źródła oficjalne, sidecar .NET, backend Python, frontend oraz testy kontraktowe.

## Najważniejszy wynik

Paczka była zasadniczo spójna po stronie Python/frontend, ale wymagała minimalnej poprawki sidecara: projekty `.csproj` były ustawione na `net11.0`, podczas gdy handoff i test integracyjny wskazują ścieżkę `.NET 8` / `net8.0`. Po audycie ustawiono:

- `sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj` -> `net8.0`,
- `sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj` -> `net8.0`,
- `tests/test_revision_sidecar_skeleton_contract.py` -> wymaga dokładnie `net8.0`,
- `sidecar/CSM.RevisionSidecar/README.md` -> opisuje aktualny, nie skeletonowy stan sidecara.

## Sprawdzone źródła zewnętrzne

- NuGet potwierdza `Clippit 3.4.3` i kompatybilność z `.NET 8.0 or higher`.
- Dokumentacja Clippit potwierdza sygnaturę `OpenXmlRegex.Replace(..., bool trackRevisions, string author)`.
- Dokumentacja Clippit potwierdza namespace `Clippit.Word` dla procesowania rewizji.
- Dokumentacja Microsoft wskazuje, że SDK danej wersji obsługuje frameworki do tej wersji; `.NET 8 SDK` nie buduje `net9.0` ani wyżej.

## Wyniki testów po poprawce

- `unzip -t`: OK.
- duplikaty ZIP: 0.
- śmieci w wejściowej paczce: 0.
- `npm run lint --silent`: PASS.
- `npm run build --silent`: PASS.
- `node --check addin/revision_bridge.js`: PASS.
- `node --check addin/taskpane.js`: PASS.
- `node --check addin/scripts/validate-static.js`: PASS.
- `python3 -m compileall -q server tests`: PASS.
- `pytest tests/test_revision_sidecar_skeleton_contract.py tests/test_revision_sidecar_contract.py`: 15 passed.
- `pytest tests/test_revision_sidecar_frontend_sync.py tests/test_revision_bridge_contract.py tests/test_word_revision_engine.py tests/test_connection_token_contract.py tests/test_frontend_backend_ux_contract.py`: 27 passed.
- `pytest tests/test_revision_sidecar_integration.py`: 5 passed, 3 skipped. Skipped = realny sidecar, bo `CSM_REVISION_SIDECAR_CMD` nie jest ustawiony i `dotnet` nie jest dostępny.

## Niepotwierdzone

- `dotnet restore`: niewykonane, `dotnet` niedostępny.
- `dotnet build`: niewykonane, `dotnet` niedostępny.
- `dotnet test`: niewykonane, `dotnet` niedostępny.
- Python -> realny sidecar przez `CSM_REVISION_SIDECAR_CMD`: niewykonane.
- Runtime Word/WebView: niewykonane.
- Instalator `.exe`: niewykonany.
- Pełny runner `python3 tests/run_pytest.py`: podjęto próbę, ale przekroczył limit czasu w środowisku audytu; nie deklarowano pełnego sukcesu.

## Wniosek

Paczka po poprawce jest lepszym kandydatem niż wejściowy ZIP, ale sidecar .NET nadal nie może zostać uznany za wykonawczo gotowy bez środowiska z .NET SDK i pełnego `restore/build/test`. Następny krok: uruchomić dokładnie:

```powershell
dotnet --info
dotnet restore sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj
dotnet build sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj -c Release
$env:CSM_REVISION_SIDECAR_CMD = "dotnet sidecar/CSM.RevisionSidecar/bin/Release/net8.0/CSM.RevisionSidecar.dll"
python -m pytest -q tests/test_revision_sidecar_integration.py
```
