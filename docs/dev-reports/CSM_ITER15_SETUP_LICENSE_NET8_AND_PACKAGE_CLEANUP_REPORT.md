# CSM v0.6.1-rc4 — audyt setupu, .NET i czystości paczki

## Cel

Sprawdzenie paczki `final6(2).zip` po walidacji Claude Code oraz poprawienie rzeczy blokujących wydanie.

## Najważniejsze ustalenia

1. `installer/CSM-Setup.iss` nie wymuszał akceptacji licencji na ekranie instalatora Inno Setup.
2. Projekty sidecara zostały przestawione z `net8.0` na `net11.0` tylko dlatego, że lokalna maszyna testowa miała .NET 11 preview. To nie jest akceptowalne jako ustawienie wydawnicze v0.6.1.
3. `global.json` dopuszczał `latestMajor`, co pozwalało na przypadkowy build na preview .NET 11 zamiast na docelowym .NET 8 LTS.
4. Paczka zawierała artefakty generowane: `__pycache__`, `.pyc`, `bin` i `obj`.
5. W paczce był też gotowy `installer/output/CSM-Setup-v0.6.1.exe`. Ponieważ skrypt instalatora został zmieniony, ten plik należy odbudować i nie wolno traktować starego EXE jako aktualnego artefaktu wydania.

## Zmiany

- Dodano `LicenseFile={#SourceDir}\LICENSE.txt` do `installer/CSM-Setup.iss`.
- Przywrócono `TargetFramework` sidecara i testów do `net8.0`.
- Przywrócono `global.json` do `rollForward: latestFeature`.
- Zaostrzono testy, aby nie akceptowały `net11.0` jako docelowego TFM dla wydania.
- Dodano test pilnujący obowiązkowej akceptacji licencji w instalatorze.
- Usunięto wygenerowane cache/build artifacts z paczki rc4.
- Usunięto stare `installer/output`, ponieważ EXE musi zostać odbudowany po zmianie skryptu instalatora.

## Status lokalnych testów

W środowisku ChatGPT nadal nie ma komendy `dotnet`, więc nie potwierdzono lokalnie `dotnet restore/build/test`.

Testy Node/Python/statyczne należy traktować jako wykonane w bieżącej sesji zgodnie z odpowiedzią w rozmowie. Finalne potwierdzenie wymaga Claude Code lub GitHub Actions na Windows z .NET 8 SDK.

## Wytyczna wydawnicza

Nie zmieniaj `net8.0` na `net11.0` dla finalnego wydania. Jeśli maszyna testowa ma tylko .NET 11 preview, należy doinstalować .NET 8 SDK albo użyć GitHub Actions `actions/setup-dotnet@v5` z `dotnet-version: 8.0.x`.

## Testy wykonane w ChatGPT po poprawkach

Przeszły:

```text
npm run lint --silent: PASS
npm run build --silent: PASS
node --check addin/revision_bridge.js: PASS
node --check addin/taskpane.js: PASS
node --check addin/scripts/validate-static.js: PASS
python3 -m compileall -q server tests: PASS
python3 -m pytest -q tests/test_release_hygiene.py tests/test_docx_negotiation_and_installer.py tests/test_installation_polish.py tests/test_support_and_setup_regressions.py: 34 passed
python3 -m pytest -q tests/test_revision_sidecar_contract.py tests/test_revision_sidecar_frontend_sync.py tests/test_word_revision_engine.py tests/test_connection_token_contract.py tests/test_frontend_backend_ux_contract.py: 34 passed
```

Niepotwierdzone w ChatGPT:

```text
dotnet restore/build/test
realny sidecar przez CSM_REVISION_SIDECAR_CMD
build nowego instalatora EXE po dodaniu LicenseFile
test ekranu licencji instalatora
test Word/WebView
```

Uwaga techniczna: część testów używających fałszywego sidecara jako podprocesu Pythona zawieszała się w tym kontenerze na komunikacji stdin/stdout. Nie interpretuję tego jako błąd CSM, bo ten sam obszar powinien być potwierdzony w środowisku Windows/.NET przez Claude Code zgodnie z plikiem `CLAUDE_CODE_TEST_SCOPE_AND_DOD_CSM_v0_6_1_rc4.md`.
