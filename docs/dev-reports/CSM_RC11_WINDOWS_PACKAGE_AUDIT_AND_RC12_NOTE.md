# Audyt paczki `CSM_v0_6_1_rc11_WINDOWS_TESTED_WITH_FAILURES.zip`

## Werdykt

Paczka jest istotnym krokiem naprzód względem wcześniejszych RC, ale nie jest jeszcze finalnym `0.6.1`.

Najważniejsze potwierdzone elementy:

- ZIP jest poprawny i czysty wydawniczo.
- Zawiera `installer/output/CSM-Setup-v0.6.1.exe`.
- Zawiera wheelhouse z paczkami `.whl` dla środowiska Python 3.12 / Windows x64.
- Sidecar jest na `net8.0`.
- Raport Claude Code potwierdza `dotnet restore/build/test` oraz integrację Python -> sidecar przez skompilowany EXE.
- Raport potwierdza instalację silent na stanie rc4/rc8.

Najważniejsze braki:

- Brak potwierdzonego interaktywnego testu Word/WebView.
- Brak potwierdzonego testu upgrade/repair z prawdziwego CSM 0.5/final2/final6.
- Brak potwierdzonego testu GUI instalatora, w którym obserwujemy brak zawieszenia paska.
- Workflow GitHub Actions używał `dotnet run` do testu sidecara, mimo że raport wskazał, że `dotnet run` powodował fałszywe błędy 503. To poprawiono w rc12: CI używa skompilowanego `CSM.RevisionSidecar.exe`.

## Lokalna weryfikacja po audycie

Przeszło lokalnie:

```text
npm run lint --silent: PASS
npm run build --silent: PASS
node --check addin/revision_bridge.js: PASS
node --check addin/taskpane.js: PASS
node --check addin/scripts/validate-static.js: PASS
python3 -m compileall -q server tests tools: PASS
testy celowane: 45 passed + 34 passed, 3 skipped
```

Pełny `pytest -q` doszedł do około 76% bez widocznych błędów, ale został przerwany limitem czasu środowiska.

## Decyzja wersjonowania

To nadal linia `0.6.1 RC`, nie `0.7`.

`0.7` powinno zacząć się po finalnym `0.6.1`, gdy celem będzie nowa funkcjonalność lub większa przebudowa, np. silnik NLP/NER, scoring ryzyka, podpis kodu, MSIX/GPO albo panel administracyjny.
