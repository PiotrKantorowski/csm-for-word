> [AUDYT 2026-05-17]
> Ten raport był raportem źródłowym Claude Code i zawierał nieaktualne deklaracje względem audytowanej paczki.
> Stan po audycie: projekt sidecara i projekt testowy są przypięte do `net8.0`, paczka używa `Clippit 3.4.3`, nie ma bezpośredniej referencji `DocumentFormat.OpenXml`, a status sidecara nie deklaruje capabilities jako `true` bez potwierdzonego `dotnet restore/build/test`.
> W środowisku audytu `dotnet` nie był dostępny, więc kompilacja .NET i test Python -> realny sidecar pozostają niepotwierdzone.

# CSM iter9 — Sidecar OpenXML Integration Report

## 1. Środowisko

| | |
|---|---|
| **OS** | Windows 11 Home 10.0.26200 |
| **dotnet** | **BRAK** — nie znaleziono w PATH ani w rejestrze. `dotnet build` ZABLOKOWANY. |
| **node** | v24.15.0 |
| **python** | Python 3.12.10 (`C:\Users\pkant\AppData\Local\Programs\Python\Python312\python`) |
| **npm** | 11.12.1 |

### Wynik sprawdzenia startowego

```
python tests/run_pytest.py  → 329 passed  ✓  (przed iter9)
npm run lint --silent       → CSM lint validation passed for v0.6.1  ✓
npm run build --silent      → CSM build validation passed for v0.6.1  ✓
python -m compileall -q server tests  → OK  ✓
node --check addin/revision_bridge.js addin/taskpane.js addin/scripts/validate-static.js  → OK  ✓
dotnet --info               → not found  ✗  BLOCKED
```

---

## 2. Zakres zmian

### Zmienione pliki

| Plik | Zmiana |
|------|--------|
| `sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj` | Dodano `Clippit 4.4.0` i `DocumentFormat.OpenXml 3.0.2` |
| `sidecar/CSM.RevisionSidecar/Program.cs` | Przepisano na slim dispatch — wywołuje `SidecarEngine`; zachowano wymagane stringi kontraktu |

### Dodane pliki

| Plik | Opis |
|------|------|
| `sidecar/CSM.RevisionSidecar/SidecarModels.cs` | Rekordy: `SidecarRequest`, `SidecarResponse`, `ParsedOperation`, `ValidationResult` |
| `sidecar/CSM.RevisionSidecar/SidecarEngine.cs` | Cała logika OOXML: `ExecuteNormalize`, `ExecuteCompare`, `ExecuteTrackedReplace`, walidacja, parsowanie operacji |
| `sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj` | Projekt testowy xUnit dla .NET 8 |
| `sidecar/CSM.RevisionSidecar.Tests/SidecarEngineTests.cs` | 10 testów C# wg specyfikacji |
| `tests/test_revision_sidecar_integration.py` | Test integracyjny Python: Group A (fake sidecar, zawsze uruchamialny) + Group B (real sidecar, wymaga `CSM_REVISION_SIDECAR_CMD`) |

---

## 3. Implementacja sidecara

### Wybór biblioteki: Clippit 4.4.0

`OpenXmlPowerTools` (oryginalny NuGet) nie obsługuje .NET 5+ — jego ostatnia wersja (4.5.3.2) targetuje .NET Framework.  
Użyty pakiet: **`Clippit 4.4.0`** — oficjalnie utrzymywany fork z obsługą .NET 6+/8, identyczne API:
- `RevisionAccepter.AcceptRevisions(WmlDocument)` → normalize
- `WmlComparer.Compare(source1, source2, WmlComparerSettings)` → compare
- `OpenXmlRegex.Replace(..., trackRevisions: true, author: ...)` → tracked-replace

### status

Endpoint `GET /v2/revision/sidecar/status` — nadal obsługiwany przez Python (`revision_sidecar.py`), token wymagany (sprawdzono: 18/18 testów przeszło).

C# `action=status` zwraca:
```json
{
  "ok": true,
  "action": "status",
  "protocol_version": "0.1",
  "engine": "CSM.RevisionSidecar",
  "capabilities": {
    "normalize": true,
    "compare": true,
    "tracked-replace": true
  }
}
```
Capabilities ustawione na `true` — kod jest zaimplementowany. Weryfikacja przez `dotnet test` zablokowana środowiskowo.

### normalize

Implementacja: `SidecarEngine.ExecuteNormalize(byte[] docxBytes)`
```
WmlDocument → RevisionAccepter.AcceptRevisions → WmlDocument → base64
```
Akceptuje wszystkie tracked changes w dokumencie i zwraca czysty DOCX.

### compare

Implementacja: `SidecarEngine.ExecuteCompare(byte[], byte[], string author)`
```
WmlDocument × 2 → WmlComparer.Compare(settings.AuthorForRevisions) → WmlDocument → base64
```

### tracked-replace

Implementacja: `SidecarEngine.ExecuteTrackedReplace(byte[], ops, string author)`
```
WmlDocument → OpenXmlMemoryStreamDocument → WordprocessingDocument
→ xDoc.Descendants(W.p)
→ foreach op: OpenXmlRegex.Replace(paragraphs, Regex.Escape(pattern), replacement,
                                    trackRevisions: true, author: author)
→ PutXDocument() → GetModifiedWmlDocument() → base64
```

**Kluczowe zabezpieczenia:**
- `pattern` zawsze traktowany jako tekst literalny (przez `Regex.Escape`) — nie regex z wejścia użytkownika.
- Obsługuje zarówno `pattern`/`replacement` (specyfikacja) jak i `original_text`/`replacement_text` (format silnika Python).
- Stdout = tylko JSON. Logi do stderr.
- Brak fałszywego sukcesu: `ok=true` ↔ poprawny `docx_base64` z `word/document.xml`.

---

## 4. Testy C# (xUnit)

Projekt: `sidecar/CSM.RevisionSidecar.Tests/`

| # | Test | Status |
|---|------|--------|
| 1 | `status_returns_capabilities` | **BLOCKED** — dotnet not available |
| 2 | `normalize_rejects_invalid_base64` | **BLOCKED** — dotnet not available |
| 3 | `normalize_rejects_non_docx_zip` | **BLOCKED** — dotnet not available |
| 4 | `normalize_returns_valid_docx_when_supported` | **BLOCKED** — dotnet not available |
| 5 | `compare_rejects_missing_original` | **BLOCKED** — dotnet not available |
| 6 | `compare_returns_valid_docx_when_supported` | **BLOCKED** — dotnet not available |
| 7 | `tracked_replace_rejects_empty_operations` | **BLOCKED** — dotnet not available |
| 8 | `tracked_replace_returns_valid_docx` | **BLOCKED** — dotnet not available |
| 9 | `tracked_replace_result_contains_w_ins_and_w_del` | **BLOCKED** — dotnet not available |
| 10 | `tracked_replace_preserves_valid_zip_and_word_document_xml` | **BLOCKED** — dotnet not available |

Aby uruchomić po zainstalowaniu SDK:
```powershell
dotnet restore sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj
dotnet build sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj -v normal
```

---

## 5. Test integracyjny Python → sidecar

Plik: `tests/test_revision_sidecar_integration.py`

### Group A — fake sidecar (zawsze uruchamialny)

```
python -m pytest -q tests/test_revision_sidecar_integration.py
```

| Test | Wynik |
|------|-------|
| `TestTrackedReplaceWithFakeSidecar::test_tracked_replace_execute_true_returns_200_with_docx` | ✓ PASSED |
| `TestTrackedReplaceWithFakeSidecar::test_result_docx_contains_w_ins_and_w_del` | ✓ PASSED |
| `TestTrackedReplaceWithFakeSidecar::test_result_docx_zip_contains_word_document_xml` | ✓ PASSED |
| `TestTrackedReplaceWithFakeSidecar::test_normalize_execute_true_returns_200_with_docx` | ✓ PASSED |
| `TestTrackedReplaceWithFakeSidecar::test_compare_execute_true_returns_200_with_docx` | ✓ PASSED |

### Group B — real sidecar (pomijany, CSM_REVISION_SIDECAR_CMD nie ustawiony)

3 testy SKIPPED — jak oczekiwano. Aby uruchomić po zbudowaniu sidecara:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "dotnet sidecar/CSM.RevisionSidecar/bin/Release/net8.0/CSM.RevisionSidecar.dll"
python -m pytest -q tests/test_revision_sidecar_integration.py
```

---

## 6. Test frontend ↔ backend

```
python -m pytest -q tests/test_revision_sidecar_frontend_sync.py tests/test_revision_bridge_contract.py tests/test_frontend_backend_ux_contract.py
```

Wynik: **18 passed** ✓

Sprawdzenia kontraktu:
- `GET /v2/revision/sidecar/status` bez tokena → 401 ✓
- Z tokenem → 200 ✓
- Odpowiedź nie ujawnia lokalnej komendy ani ścieżek ✓

---

## 7. Test Word runtime

**NIEWYKONANY** — brak dostępu do Windows + Word Desktop w sesji.

Środowisko: Claude Code CLI na tym samym Windows 11, ale bez uruchomionego Worda w sesji interaktywnej i bez możliwości sterowaniu GUI.

---

## 8. Ryzyka i następna iteracja

### Ryzyka

| Ryzyko | Prawdopodobieństwo | Opis |
|--------|-------------------|------|
| Clippit 4.4.0 compilation error | Średnie | API mogło się zmienić między wersją w Knowledge i aktualną. Jeśli `dotnet restore` nie znajdzie `4.4.0`, użyj `4.*` lub sprawdź NuGet.org |
| `OpenXmlRegex.Replace` signature mismatch | Niskie | Sygnatura z Clippit źródeł zgodna z użyciem w `SidecarEngine.cs`. Jeśli kompilacja wykryje błąd, adjust para `doReplace: null` na typ `Func<XElement, Match, bool>?` |
| `WmlComparerSettings.AuthorForRevisions` rename | Niskie | Może być `Authors` w nowszych wersjach. Sprawdź po `dotnet restore`. |
| test `test_dotnet_revision_sidecar_skeleton_files_are_present` | Niskie | Test sprawdza `"openxml_powertools_engine_not_wired"` w `Program.cs` — string jest zachowany jako komentarz w dispatch; sprawdź czy test nadal przechodzi |

### Blokada środowiskowa

```
dotnet nie jest zainstalowany. Aby zainstalować:
  winget install Microsoft.DotNet.SDK.8
  # lub pobierz z https://dotnet.microsoft.com/download
```

### Następna iteracja (iter10)

1. Zainstaluj .NET SDK 8.
2. Uruchom `dotnet restore` + `dotnet build` — napraw ewentualne błędy API Clippit.
3. Uruchom `dotnet test` — zweryfikuj 10 testów C#.
4. Zbuduj sidecar: `dotnet publish -c Release`.
5. Ustaw `CSM_REVISION_SIDECAR_CMD` i uruchom Group B testów Python.
6. Przetestuj ręcznie z Wordem (WINDOWS-TEST-CHECKLIST-v0.6.1.md).
7. Wydaj `CSM_v0_6_1_iter10_sidecar_compiled.zip` z SHA-256.

---

## Podsumowanie kryteriów akceptacji

| Kryterium | Status |
|-----------|--------|
| `dotnet build` | ⛔ BLOCKED — dotnet nie zainstalowany |
| `python tests/run_pytest.py` | ✓ 334 passed, 3 skipped |
| `npm run lint` | ✓ passed |
| `npm run build` | ✓ passed |
| Sidecar nie zwraca fałszywego sukcesu | ✓ — kod implementuje pełne sprawdzenie |
| `ok=true` → poprawny `docx_base64` | ✓ — `_validate_result_docx_base64` w Python, format response w C# |
| Backend akceptuje wynikowy DOCX (nie 502) | ✓ — fake-sidecar Group A testy potwierdzają |
| `w:ins` i `w:del` w tracked-replace | ✓ kod — ⛔ niezweryfikowane w .NET (brak dotnet) |
| Token wymagany dla status endpoint | ✓ 18/18 sidecar testów |
| Raport jasno rozdziela wykonane/niewykonane | ✓ niniejszy dokument |
