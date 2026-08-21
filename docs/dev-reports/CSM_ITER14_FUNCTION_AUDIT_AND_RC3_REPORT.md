# CSM iteracja 14 — globalny audyt funkcji i v0.6.1-rc3

Data: 2026-05-18

## Cel

Rozbić CSM na główne funkcje, sprawdzić najważniejsze wzorce i ryzyka dla każdej funkcji w źródłach GitHub/oficjalnych, przejrzeć kod, wdrożyć poprawki i ponowić pełne sprawdzenie.

## Funkcje objęte audytem

1. Word Add-in / Office.js: komunikacja z dokumentem, tryb śledzenia zmian, widoczny tekst, zakresy Worda.
2. Trwała mapa anonimizacji: CustomXmlPart, settings, metadane dokumentu.
3. Backend Python: anonimizacja, restore, walidacja DOCX/ZIP/base64, raporty i błędy publiczne.
4. Program pomocniczy .NET: normalize, compare, tracked-replace, stdin/stdout JSON.
5. Zachowanie śledzenia zmian: OpenXmlRegex.Replace(trackRevisions=true) i walidacja w:ins/w:del.
6. Bezpieczeństwo lokalnego API: token, redakcja komend i ścieżek, brak PII w audycie.
7. UX dla prawników: komunikaty bez żargonu typu sidecar/OOXML/capabilities.
8. CI/release: GitHub Actions, .NET 8, Node, Python, build instalatora, czystość paczki.
9. Dystrybucja i dokumentacja: release notes, checklista Windows, instrukcja.

## Sprawdzone źródła referencyjne

- OfficeDev office-js-snippets: manage-change-tracking.yaml — changeTrackingMode i getReviewedText.
- OfficeDev office-js-snippets: manage-custom-xml-part-ns.yaml — CustomXmlPart, namespace, settings.
- OfficeDev office-js-snippets: get-change-tracking-states.yaml — content controls i stany śledzenia zmian.
- sergey-tihon/Clippit: OpenXmlRegex.cs — Replace z trackRevisions i author.
- sergey-tihon/Clippit: RevisionAccepter.cs — AcceptRevisions i detekcja tracked revisions.
- OpenXmlDev/Open-Xml-PowerTools: WmlComparer.cs — porównywanie dokumentów i rewizje.
- actions/setup-dotnet README — setup .NET SDK w GitHub Actions, dotnet-version i global.json.
- fastapi/fastapi docs security — APIKeyHeader jako właściwy wzorzec tokenowego zabezpieczenia lokalnego API.

## Wyniki audytu

### OK

- Word Add-in ma logiczny podział na bridge, taskpane i word-bridge.
- Mapa anonimizacji jest trwale wiązana z dokumentem przez CustomXmlPart/settings.
- Backend waliduje odpowiedzi programu pomocniczego: sukces akcji wykonawczej wymaga poprawnego pliku Word.
- Status mechanizmu zachowania śledzenia zmian jest zabezpieczony tokenem i redaguje lokalną komendę.
- Komunikaty użytkownika są w większości napisane językiem prawniczo-użytkowym, nie programistycznym.
- CI ma już Node, Python, .NET i test realnego programu pomocniczego przez CSM_REVISION_SIDECAR_CMD.

### Poprawione w tej iteracji

1. Program pomocniczy .NET dla `tracked-replace` nie ogranicza się już tylko do głównej treści `word/document.xml`. Obejmuje teraz także:
   - dokument główny,
   - nagłówki,
   - stopki,
   - przypisy dolne,
   - przypisy końcowe,
   - komentarze Worda.

2. Dodano test C# `tracked_replace_covers_headers_and_footers`, który wymaga rewizji `w:ins` i `w:del` również w nagłówku i stopce.

3. Dodano statyczny test Python potwierdzający, że sidecar obejmuje najważniejsze części tekstowe dokumentu Word.

4. Dodano `global.json`, żeby repozytorium jasno deklarowało .NET 8:

```json
{
  "sdk": {
    "version": "8.0.100",
    "rollForward": "latestFeature"
  }
}
```

5. Workflow GitHub Actions używa teraz `global-json-file: global.json` przy `actions/setup-dotnet@v5`.

6. Zaktualizowano dwa testy, które wymagały starych technicznych komunikatów. Testy nadal pilnują zachowania, ale nie wymuszają żargonu w UI.

## Testy wykonane

- `npm run lint --silent` — PASS
- `npm run build --silent` — PASS
- `node --check addin/revision_bridge.js` — PASS
- `node --check addin/taskpane.js` — PASS
- `node --check addin/scripts/validate-static.js` — PASS
- `python3 -m compileall -q server tests` — PASS
- `python3 -m pytest -q` — PASS: 340 passed, 3 skipped

## Testy niepotwierdzone w tym środowisku

- `dotnet --info` — FAIL: dotnet: command not found
- `dotnet restore`
- `dotnet build`
- `dotnet test`
- realny test Word/WebView
- build instalatora `.exe`

## Wniosek

To jest sensowny kandydat `v0.6.1-rc3`: funkcjonalnie dojrzalszy niż rc2, bo program pomocniczy .NET nie pomija już nagłówków, stopek i przypisów przy operacji tracked-replace. Nadal finalne 0.6.1 wymaga potwierdzenia w środowisku z .NET 8 SDK i w Wordzie.
