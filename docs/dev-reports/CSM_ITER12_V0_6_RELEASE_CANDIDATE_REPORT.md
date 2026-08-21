# CSM iteracja 12 — kandydat v0.6.1

## Cel

Przekształcenie działającej linii 0.5.10 w formalny kandydat v0.6.1 bez zmiany głównego algorytmu anonimizacji.

## Zakres zmian

- Podbito aktywną wersję z 0.5.0 do 0.6.1 w `VERSION.json`, `package.json`, `addin/package.json`, manifeście Office, instalatorze i testach kontraktowych.
- Zmieniono nazwy aktualnych dokumentów wydania na `v0.6.1`.
- Zaktualizowano instrukcję DOCX, release notes i checklistę Windows.
- Zachowano komunikaty przyjazne prawnikom z iteracji 11.
- Nie zmieniano głównego algorytmu anonimizacji.

## Ważne ograniczenie

W tym środowisku nie ma komendy `dotnet`, dlatego nie można tu uczciwie potwierdzić `dotnet restore`, `dotnet build`, `dotnet test` ani pełnego testu Word → backend → program pomocniczy → Word.

## Decyzja wersjonowania

Ta paczka może być traktowana jako `0.6.1-rc1` albo jako `0.6.1` po zewnętrznym potwierdzeniu testów .NET/Word.


## Testy wykonane w kontenerze

- `npm run lint --silent`: PASS
- `npm run build --silent`: PASS
- `node --check addin/revision_bridge.js`: PASS
- `node --check addin/taskpane.js`: PASS
- `node --check addin/scripts/validate-static.js`: PASS
- `python3 -m compileall -q server tests`: PASS
- render instrukcji `Instrukcja_CSM_v0_6_1.docx`: PASS, 2 strony, bez widocznych problemów układu na PNG
- testy release/manifest/instrukcja/UI: 42 passed
- testy sidecar/status/frontend/token/UX: 33 passed
- pełny zestaw testów uruchomiony w grupach: 73 passed + 61 passed + 76 passed, 3 skipped + 60 passed + 67 passed

## Testy niewykonane w kontenerze

- `dotnet --info`: FAIL środowiskowy — `dotnet: command not found`
- `dotnet restore/build/test`: niewykonane z powodu braku .NET SDK
- realny `CSM_REVISION_SIDECAR_CMD`: 3 testy integracyjne pominięte, bo zmienna nie jest ustawiona
- runtime Microsoft Word/WebView: niewykonany w tym środowisku

## Wniosek

Kod i paczka są przygotowane jako kandydat `v0.6.1`. Formalne oznaczenie jako stabilne `v0.6.1` zależy od zewnętrznego potwierdzenia testów .NET i Word runtime.
