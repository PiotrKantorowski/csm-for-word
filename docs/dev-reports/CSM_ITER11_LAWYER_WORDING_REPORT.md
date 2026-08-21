# CSM — iteracja 11: uproszczenie komunikatów dla użytkowników prawniczych

## Cel

Ta iteracja jest krokiem pośrednim przed oznaczeniem wydania jako 0.6. Celem było usunięcie z widocznych komunikatów języka technicznego, który może być nieczytelny dla prawników i osób nietechnicznych.

## Najważniejsza zmiana

W panelu użytkownika i publicznych komunikatach błędów zastąpiono określenia techniczne:

- „sidecar rewizji OOXML”,
- „capabilities”,
- „sonda statusu”,
- „wykonywalny odnaleziony”,
- „polecenie skonfigurowane”,
- „odpowiedź sidecara”,

prostszymi komunikatami:

- „mechanizm zachowania śledzenia zmian”,
- „program pomocniczy”,
- „sprawdzenie uruchomienia”,
- „obsługiwane funkcje”,
- „moduł odpowiada”.

## Zakres zmian

Zmieniono:

- `addin/taskpane.html`,
- `addin/taskpane.js`,
- `server/api.py`,
- `server/revision_sidecar.py`,
- `tests/test_revision_sidecar_frontend_sync.py`,
- `tests/test_revision_sidecar_contract.py`,
- `tests/test_revision_sidecar_skeleton_contract.py`.

## Status wersji

Nie oznaczono tej paczki jako pełne 0.6, ponieważ ta iteracja dotyczy języka komunikatów i gotowości UX. Formalne 0.6 powinno zostać nadane po końcowym potwierdzeniu środowiskowym, w szczególności po testach .NET i/lub po potwierdzonym teście w Wordzie.

## Ograniczenia

W tym środowisku nadal nie potwierdzono:

- `dotnet restore`,
- `dotnet build`,
- `dotnet test`,
- pełnego runtime Word/WebView.


## Testy wykonane w tej iteracji

Przeszły:

```text
python3 -m compileall -q server tests
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
python3 -m pytest -q tests/test_revision_sidecar_frontend_sync.py tests/test_revision_sidecar_contract.py tests/test_revision_sidecar_skeleton_contract.py
python3 -m pytest -q tests/test_revision_sidecar_integration.py tests/test_revision_bridge_contract.py tests/test_word_revision_engine.py tests/test_connection_token_contract.py tests/test_frontend_backend_ux_contract.py tests/test_runtime_wording_is_stable.py tests/test_polish_release_contract.py tests/test_distribution_polish.py tests/test_release_hygiene.py
```

Wynik łączny uruchomionych grup testowych:

```text
21 passed
50 passed, 3 skipped
```

Trzy pominięte testy dotyczą realnego sidecara .NET i wymagają ustawienia `CSM_REVISION_SIDECAR_CMD`.

Pełny runner `python3 tests/run_pytest.py` został uruchomiony, ale nie zakończył się w limicie środowiska. Zanim został przerwany, raportował postęp do około 63% i nie pokazał błędów w widocznej części logu. Nie traktuję tego jako pełnego zaliczenia runnera.

`dotnet --info` w tym środowisku nadal zwraca `dotnet: command not found`, więc nie potwierdzono lokalnie `dotnet restore/build/test`.
