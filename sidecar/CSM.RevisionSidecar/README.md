# CSM.RevisionSidecar

Sidecar rewizyjny CSM pracujący przez protokół `stdin/stdout JSON`. Projekt jest przypięty do `net8.0` i używa pakietu `Clippit 3.4.3` jako utrzymywanego forka OpenXmlPowerTools.

## Akcje

- `status` — odpowiedź diagnostyczna sidecara; dla uruchomionego sidecara raportuje `supported_actions` oraz capabilities `normalize`, `compare`, `tracked-replace`.
- `normalize` — `RevisionAccepter.AcceptRevisions(WmlDocument)`.
- `compare` — `WmlComparer.Compare(...)`.
- `tracked-replace` — `OpenXmlRegex.Replace(..., trackRevisions: true, author: ...)` dla literalnych operacji tekstowych.

## Protokół

Wejście: pojedynczy obiekt JSON na `stdin` zgodny z `server/revision_sidecar.py`, m.in. `protocol_version`, `action`, `docx_base64`, `revised_docx_base64`, `operations`, `author`, `map_id`.

Wyjście: pojedynczy obiekt JSON na `stdout`. Backend Pythona odrzuca sukces akcji wykonawczej, jeżeli odpowiedź nie zawiera poprawnego `docx_base64` będącego pakietem DOCX z `word/document.xml`. Endpoint `/v2/revision/sidecar/status` wykonuje teraz sondę `action=status`, więc odróżnia samo odnalezienie komendy od faktycznej odpowiedzi sidecara.

## Walidacja .NET

W środowisku z .NET 8 SDK uruchom:

```powershell
dotnet restore sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj
dotnet build sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj -c Release
```

Po zbudowaniu:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "dotnet sidecar/CSM.RevisionSidecar/bin/Release/net8.0/CSM.RevisionSidecar.dll"
python -m pytest -q tests/test_revision_sidecar_integration.py
```

W środowisku, w którym przygotowano ten audyt, `dotnet` nie był dostępny, więc nie potwierdzono kompilacji ani realnego wykonania sidecara .NET.
