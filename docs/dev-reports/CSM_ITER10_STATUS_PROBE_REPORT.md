# CSM — iteracja 10: status-probe sidecara pod 0.6-rc

Data: 2026-05-17

## Cel iteracji

Po potwierdzeniu, że poprzednia paczka działa w środowisku użytkownika, wykonano kolejną małą iterację w kierunku `0.6-rc`: poprawiono diagnostykę realnego sidecara .NET.

Poprzedni backend sprawdzał głównie, czy `CSM_REVISION_SIDECAR_CMD` jest ustawione i czy pierwszy element komendy da się odnaleźć. To nie wystarczało do odróżnienia sytuacji:

- komenda istnieje, ale sidecar nie startuje,
- sidecar startuje, ale zwraca zły protokół,
- sidecar startuje i realnie deklaruje obsługiwane akcje oraz capabilities.

## Zmienione pliki

- `server/revision_sidecar.py`
- `server/api.py`
- `addin/taskpane.js`
- `sidecar/CSM.RevisionSidecar/Program.cs`
- `sidecar/CSM.RevisionSidecar/README.md`
- `tests/test_revision_sidecar_contract.py`
- `tests/test_revision_sidecar_frontend_sync.py`
- `CSM_ITER10_STATUS_PROBE_REPORT.md`

## Co dodano

### 1. Sonda statusu sidecara

Endpoint:

```text
GET /v2/revision/sidecar/status
```

nie ogranicza się już do sprawdzenia ścieżki/komendy. Backend wykonuje sondę:

```json
{"protocol_version":"0.1","action":"status"}
```

i sprawdza, czy sidecar zwraca poprawny JSON, zgodny `protocol_version`, brak `ok=false` oraz pola diagnostyczne.

### 2. Nowe pola statusu

Do statusu dodano m.in.:

```text
reachable
probe_status
engine
capabilities
supported_actions
```

Dzięki temu UI i API mogą rozróżnić:

- `configured` — komenda jest ustawiona,
- `executable_resolved` — wykonywalny plik został odnaleziony,
- `reachable` — sidecar faktycznie odpowiedział na sondę,
- `capabilities` — co sidecar deklaruje jako gotowe.

### 3. Redakcja poufnych ścieżek nadal działa

Pełne `CSM_REVISION_SIDECAR_CMD` i ścieżka wykonywalna nadal są redagowane w API:

```text
command -> <redacted>
executable -> <redacted>
```

Dodano test, który sprawdza, że nawet przy błędnej sondzie statusu ścieżka fake-sidecara nie wycieka do odpowiedzi HTTP.

### 4. Frontend pokazuje lepszy status techniczny

`taskpane.js` pokazuje teraz w diagnostyce:

- status sondy,
- czy sidecar odpowiedział,
- capabilities,
- dotychczasowe informacje o konfiguracji i akcjach.

### 5. C# sidecar raportuje capabilities dla realnego `action=status`

Dla poprawnego żądania JSON `action=status` sidecar C# zwraca capabilities `true` dla:

```text
normalize
compare
tracked-replace
```

Pusty stdin pozostaje prostym health-checkiem harnessu i nie deklaruje pełnych capabilities.

## Testy wykonane

### ZIP / higiena przed zmianą

- wejściowy ZIP był poprawny,
- liczba wpisów wejściowych: 269,
- duplikaty: 0,
- śmieci/cache w wejściowej paczce: 0.

### Frontend / JS

```text
npm run lint --silent: PASS
npm run build --silent: PASS
node --check addin/revision_bridge.js: PASS
node --check addin/taskpane.js: PASS
node --check addin/scripts/validate-static.js: PASS
```

### Python / testy celowane

```text
python3 -m compileall -q server tests: PASS
pytest tests/test_revision_sidecar_contract.py tests/test_revision_sidecar_skeleton_contract.py tests/test_revision_sidecar_frontend_sync.py: 20 passed
pytest tests/test_revision_bridge_contract.py tests/test_word_revision_engine.py tests/test_connection_token_contract.py tests/test_frontend_backend_ux_contract.py: 24 passed
pytest tests/test_revision_sidecar_integration.py: 5 passed, 3 skipped
```

`3 skipped` dotyczą realnego sidecara .NET, ponieważ w tym środowisku nie ustawiono `CSM_REVISION_SIDECAR_CMD` i nie ma `dotnet`.

### Pełny runner

Podjęto próbę:

```text
python3 tests/run_pytest.py
```

Runner przekroczył limit czasu środowiska po przejściu dużej części testów. Nie deklarowano pełnego sukcesu całego runnera.

### .NET

```text
dotnet --info: dotnet: command not found
```

W tym środowisku nadal nie da się potwierdzić:

- `dotnet restore`,
- `dotnet build`,
- `dotnet test`,
- Python -> realny sidecar przez skompilowany `CSM_REVISION_SIDECAR_CMD`,
- Word/WebView runtime,
- pełne E2E Word -> backend -> sidecar -> Word.

## Wniosek

Ta iteracja nie zmienia głównego algorytmu anonimizacji ani restore. Poprawia natomiast warstwę diagnostyczną potrzebną do `0.6`: backend i UI potrafią teraz odróżnić sidecar tylko skonfigurowany od sidecara realnie odpowiadającego i deklarującego capabilities.

Rekomendowana nazwa paczki roboczej: `CSM_v0_5_9_iter10_status_probe.zip`. Jest to techniczny kandydat w kierunku `0.6-rc`, ale wewnętrzne `VERSION.json` i manifest pozostają na linii `0.6.1`, żeby nie mieszać wersjonowania release przed formalnym domknięciem pełnego `.NET build/test` oraz E2E.
