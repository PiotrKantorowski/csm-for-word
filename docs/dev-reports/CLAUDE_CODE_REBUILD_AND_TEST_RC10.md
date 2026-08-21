# Claude Code instructions — rebuild and verify CSM v0.6.1 rc10

## Input

Use this source package only:

```text
CSM_v0_6_1_rc10_install_reversibility_hardening_SOURCE.zip
```

Do not reuse any previous `CSM-Setup-v0.6.1.exe`. The old EXE does not contain the rc10 installer watchdog and pseudonymization fixes.

## Goal

Build a fresh Windows installer and verify that CSM 0.6 is reliable on machines other than the development computer, especially after old 0.5 installations.

## Build steps

From the unpacked rc10 source root:

```powershell
Get-FileHash .\CSM_v0_6_1_rc10_install_reversibility_hardening_SOURCE.zip -Algorithm SHA256
powershell -ExecutionPolicy Bypass -File .\installer\build-csm-setup.ps1
Get-FileHash .\installer\output\CSM-Setup-v0.6.1.exe -Algorithm SHA256
```

Then package the verified source plus the newly built EXE as:

```text
CSM_v0_6_1_rc10_WINDOWS_VERIFIED.zip
```

## Required static checks

Run:

```powershell
python -m compileall -q server tests tools
python -m pytest -q tests/test_rc10_install_and_reversibility_hardening.py tests/test_rc8_install_and_common_word_regressions.py tests/test_installer_runtime_resilience_rc7.py tests/test_installer_resilience_matrix.py tests/test_final_assets_cache_and_mapping_ux.py tests/test_release_hygiene.py
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
```

DoD:

- zero failed tests;
- no active rc7/rc8/rc9 UI labels in manifest/taskpane/install script;
- no `node_modules`, `bin`, `obj`, `__pycache__`, `.pyc`, `.pytest_cache` in the ZIP;
- installer references `LicenseFile={#SourceDir}\LICENSE.txt`.

## Required .NET checks

Run:

```powershell
dotnet --info
dotnet restore .\sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
dotnet build .\sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
dotnet test .\sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release
```

DoD:

- sidecar remains `net8.0`;
- no `net11.0` in active csproj/global.json;
- `dotnet test` passes.

## Required Python -> real sidecar test

Set:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "dotnet run --project sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj --"
python -m pytest -q tests/test_revision_sidecar_integration.py
```

DoD:

- no skipped real-sidecar tests;
- no false `ok=true` without a valid DOCX;
- returned DOCX is a ZIP and contains `word/document.xml`.

## Clean install test

Use a Windows user profile that has no previous CSM installation.

Steps:

1. Run the rebuilt `installer\output\CSM-Setup-v0.6.1.exe`.
2. Accept the GUI license.
3. Let the installer finish.
4. Do not type anything in hidden consoles.
5. Run `C:\CSM\tools\diagnose-csm.ps1`.
6. Open Word and load the CSM add-in.

DoD:

- installer does not hang near the end;
- if a child step stalls, installer fails with logs instead of hanging;
- `%TEMP%\CSM-install.log` exists;
- `%TEMP%\CSM-setup-once.log` exists;
- `C:\CSM\server\.venv\Scripts\python.exe` exists;
- `fastapi`, `uvicorn`, `pydantic`, and `lxml` import successfully in the venv;
- backend listens on `127.0.0.1:8787`;
- add-in server listens on `https://localhost:3000`;
- certificate diagnostic shows `trusted=True`;
- Word does not show the blocked-content warning for the CSM add-in;
- Word panel shows rc10, not rc7/rc8/rc9 or 0.5/final2/final6.

## Upgrade / repair test after 0.5

Use a machine/profile that had CSM 0.5 installed or simulate the old state:

- existing `C:\CSM`;
- old Word trusted catalog;
- old Office cache;
- stale or missing localhost certificate;
- incomplete `.venv` or venv missing `fastapi`/`uvicorn`.

Run the rebuilt rc10 EXE.

DoD:

- installer cleans/repairs the old state;
- no hidden license prompt blocks setup;
- old 0.5/final2/final6 cache busters are not loaded by Word after refresh;
- `.venv` is rebuilt or repaired;
- backend and add-in server start;
- diagnostic PASS-equivalent state after repair.

## Pseudonymization tests in Word

Test at minimum these text cases in Word and via backend where possible:

```text
Działając w imieniu Klienta – OLIMP LABORATORIES, Pustynia 84F, 39-200 Dębica; wzywam Pana Jana Muchę do zapłaty.

Powód: "OLIMP LABORATORIES" z siedzibą w Pustyni, NIP: 1234567890.

na rzecz Pani Iwony Teresy Ustrzyckiej (PESEL: 90010112345)

Patryk Mucha i Renata Mucha obejmują udziały.

WEZWANIE DO ZAPŁATY – OSTATECZNE PRZEDSĄDOWE
```

DoD:

- `OLIMP LABORATORIES` is masked in party/client contexts;
- `Pustynia 84F` and `Pustyni` are masked in address/seat contexts;
- `Jana Muchę`, `Patryk Mucha`, `Renata Mucha`, and `Iwony Teresy Ustrzyckiej` are masked;
- generic heading `WEZWANIE DO ZAPŁATY – OSTATECZNE PRZEDSĄDOWE` is not incorrectly masked as a company;
- restore returns the original text from the generated map;
- no unresolved placeholders remain after restore unless user edited them manually.

## Required report

Create a report inside the final ZIP:

```text
CLAUDE_CODE_RC10_WINDOWS_VERIFICATION_REPORT.md
```

The report must include:

- source ZIP SHA-256;
- rebuilt EXE SHA-256;
- final ZIP SHA-256;
- exact commands run;
- clean install result;
- upgrade/repair result;
- dotnet results;
- real sidecar result;
- Word/WebView result;
- pseudonymization/restore result;
- list of failures or uncertainty.

Do not call the package `WINDOWS_VERIFIED` unless the clean install, upgrade/repair, dotnet, real sidecar, and Word/WebView tests are actually completed and documented.
