# Claude Code instructions — rebuild and verify CSM v0.6.1 rc9

## Input package
Use only:

```text
CSM_v0_6_1_rc9_source_fix_title_genitive_and_labels.zip
```

Do not reuse the previous rc8 EXE. The rc8 EXE is stale because rc9 changes source files used by the installer and anonymization engine.

## Goal
Produce a new Windows-verified package with a freshly rebuilt installer and a complete verification report.

Expected output package name:

```text
CSM_v0_6_1_rc9_WINDOWS_VERIFIED.zip
```

## Critical fixes to verify

1. `setup.exe` must not freeze at the final progress bar.
2. The hidden `AKCEPTUJE` prompt must not appear in the GUI installer path.
3. Installation from GUI must run user-profile setup as the original user, not the elevated administrator profile.
4. The installer log must show `CSM v0.6.1 rc9`, not `rc7`, `final2`, or `v0.5.0`.
5. The Word add-in must load without the blocked-content/certificate warning.
6. The anonymization engine must mask ordinary-word names and localities, including:
   - `Jan Mucha`, `Renata Mucha`, `Patryk Muchy`,
   - `Pustynia 84F, 39-200 Dębica`,
   - `Anna Pustynia`,
   - `Meble New Concept Sp. z o.o.`,
   - `Pani Iwony Teresy Ustrzyckiej (PESEL: ...)`.

## Commands to run

From the unpacked rc9 source root:

```powershell
npm ci
npm run lint --silent
npm run build --silent
python -m pip install -r server\requirements.txt
python -m compileall -q server tests tools
python -m pytest -q tests\test_rc8_install_and_common_word_regressions.py
python -m pytest -q tests\test_release_hygiene.py tests\test_distribution_polish.py
python -m pytest -q --tb=no
```

.NET sidecar:

```powershell
$DOTNET = "C:\Program Files\dotnet\dotnet.exe"
& $DOTNET --info
& $DOTNET restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
& $DOTNET build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
& $DOTNET test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release
$env:CSM_REVISION_SIDECAR_CMD = (Resolve-Path "sidecar\CSM.RevisionSidecar\bin\Release\net8.0\CSM.RevisionSidecar.exe").Path
python -m pytest -q tests\test_revision_sidecar_integration.py
```

Rebuild installer:

```powershell
Remove-Item -Recurse -Force .\installer\output -ErrorAction SilentlyContinue
& "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe" installer\CSM-Setup.iss
Get-FileHash .\installer\output\CSM-Setup-v0.6.1.exe -Algorithm SHA256
```

## Manual Windows tests

### A. Clean install

On a fresh Windows profile or clean VM:

1. Run the rebuilt `CSM-Setup-v0.6.1.exe`.
2. Confirm the license screen appears and blocks installation until accepted.
3. Confirm the installer completes and does not freeze at the final progress bar.
4. Run CSM diagnostics.
5. Confirm:
   - `.venv\Scripts\python.exe` exists,
   - `fastapi`, `uvicorn`, `pydantic`, `lxml` imports pass,
   - `localhost` certificate exists and is trusted,
   - port 3000 listens for add-in HTTPS,
   - port 8787 listens for backend,
   - `/health` returns status ok and version `0.6.1`.

### B. Upgrade/repair from CSM 0.5

On a profile containing old CSM 0.5/final2/final6 state:

1. Run the rebuilt rc9 installer.
2. Confirm old cache is removed.
3. Confirm stale certificate state is repaired.
4. Confirm stale or broken `.venv` is repaired.
5. Confirm no visible log/status says `v0.5.0`, `final2`, or `final6` as the active installed version.
6. Confirm Word loads the CSM add-in without the blocked-content/certificate warning.

### C. Word anonymization test

Use real Word, not only unit tests.

Test documents must include at least:

```text
Jan Mucha
Renata Mucha
Patryka Muchy
Pani Iwony Teresy Ustrzyckiej (PESEL: ...)
Pustynia 84F, 39-200 Dębica
Anna Pustynia
Meble New Concept Sp. z o.o.
```

Definition of Done:

1. None of those names/localities/company fragments remain visible after anonymization.
2. The output DOCX opens without Word repair.
3. If tracked changes mode is used, Word displays changes correctly.
4. Restore still works on a document anonymized by rc9.

## Required report

Create:

```text
CLAUDE_CODE_RC9_WINDOWS_VERIFICATION_REPORT.md
```

The report must include:

1. Input ZIP SHA-256.
2. Output ZIP SHA-256.
3. Output EXE SHA-256.
4. Full test results, including failed/skipped tests.
5. `dotnet --info` summary.
6. Whether clean install passed.
7. Whether upgrade/repair from CSM 0.5 passed.
8. Whether Word/WebView passed.
9. Whether anonymization samples passed.
10. Screenshots/log excerpts if anything failed.

Do not call the package `WINDOWS_VERIFIED` unless clean install, upgrade/repair, Word/WebView, and anonymization smoke tests actually passed.
