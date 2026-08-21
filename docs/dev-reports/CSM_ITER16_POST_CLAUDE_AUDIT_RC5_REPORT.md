# CSM v0.6.1-rc5 — audyt paczki po Claude Code

## Cel

Audyt paczki `final6(3).zip` po zmianach Claude Code, ze szczególnym uwzględnieniem:

- obowiązkowej akceptacji licencji w instalatorze,
- stabilizacji sidecara na `.NET 8`,
- czystości paczki,
- testów automatycznych Node/Python,
- tego, co nadal wymaga środowiska Windows / Claude Code.

## Ustalenia

1. `installer/CSM-Setup.iss` zawiera `LicenseFile={#SourceDir}\LICENSE.txt` przed sekcją `[Files]`.
2. `installer/output/CSM-Setup-v0.6.1.exe` jest obecny i według metadanych ZIP został zbudowany po aktualizacji `CSM-Setup.iss`.
3. Projekty sidecara są ustawione na `net8.0`.
4. `global.json` wymusza linię `.NET 8` przez `version: 8.0.100` i `rollForward: latestFeature`.
5. W paczce po Claude Code pozostały artefakty build/cache: `bin`, `obj`, `__pycache__`, `.pyc` oraz testowy `tools/test_full_docx_output.docx`.
6. `npm run lint --silent` nie przechodził, ponieważ `install-guide.html` nie zawierał nazwy aktualnego instalatora `CSM-Setup-v0.6.1.exe`.

## Zmiany w rc5

- Dodano w `install-guide.html` informację o aktualnym instalatorze: `CSM-Setup-v0.6.1.exe`.
- Usunięto artefakty `bin`, `obj`, `__pycache__`, `.pyc`, `.pytest_cache` oraz testowy plik `tools/test_full_docx_output.docx`.
- Dodano test `test_v060_source_package_does_not_include_build_outputs`, który pilnuje, żeby paczka źródłowa nie zawierała build/cache artifacts. Wyjątkiem jest `installer/output`, bo może zawierać finalny artefakt instalatora.
- Zachowano `installer/output/CSM-Setup-v0.6.1.exe` jako artefakt wydania po stronie Windows, ale nie potwierdzono go graficznie w tym środowisku.

## Testy wykonane w ChatGPT

- `unzip -t`: PASS
- `npm run lint --silent`: PASS
- `npm run build --silent`: PASS
- `node --check addin/revision_bridge.js`: PASS
- `node --check addin/taskpane.js`: PASS
- `node --check addin/scripts/validate-static.js`: PASS
- `python3 -m compileall -q server tests`: PASS
- testy release/installer/support: PASS
- testy revision/frontend/backend/token/UX: PASS

## Niepotwierdzone w ChatGPT

- `dotnet restore/build/test`, ponieważ w środowisku ChatGPT nie ma `dotnet`,
- graficzny test instalatora Inno Setup,
- blokada instalacji bez akceptacji licencji,
- test Word Add-in w rzeczywistym Microsoft Word / WebView,
- realny build instalatora po stronie CI/Windows poza dostarczonym EXE.

## Werdykt

`v0.6.1-rc5` jest czystszą paczką po audycie. Kodowo mogę przejąć dalsze porządki, ale finalne zamknięcie `v0.6.1` nadal wymaga testów Windows/Word opisanych w pliku `CLAUDE_CODE_TEST_SCOPE_AND_DOD_CSM_v0_6_1_rc5.md`.
