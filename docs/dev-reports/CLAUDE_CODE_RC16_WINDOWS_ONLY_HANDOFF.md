# Claude Code — CSM v0.6.1 rc16 Windows-only handoff

Date: 2026-05-19
Source package to test/build: `CSM_v0_6_1_rc16_LOCAL_SOURCE.zip`
Status: source candidate only; do not mark as final unless all Windows/Word/Inno/.NET gates pass.

## Important instruction

Do not redo general source refactoring or pseudonymization work unless a Windows test reveals a reproducible blocker. The source has already passed local Python/Node/static checks. Your task is limited to gates that cannot be verified in the current Linux/container environment.

## Current active labels to verify

After unpacking the source, confirm these active markers:

- `VERSION.json` contains `v0.6.1-rc16-local-hygiene-20260519`.
- `addin/taskpane.html` shows `v0.6.1 — rc16`.
- `addin/manifest.xml` uses `20260519-rc16` cache busters.
- `tools/install-csm.ps1` says `CSM v0.6.1 rc16`.
- `server/redactor.py` reports engine version `0.2.45-rc16-local-hygiene`.
- Active add-in asset URLs use `icon-*-csm-rc16.png` and `logo-csm-primary-rc16.png`, not `final6` asset filenames.

## Local checks already performed before handoff

The source was locally validated with:

```powershell
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
python -m compileall -q server tests tools
python tools/evaluate_pseudonymization_grid.py
python -m pytest -q tests/test_release_hygiene.py tests/test_rc16_mapping_grid_and_headings.py
```

A chunked run of the Python test suite produced:

```text
387 passed, 3 skipped
```

The 3 skips are expected unless `CSM_REVISION_SIDECAR_CMD` points to a compiled real sidecar EXE.

## Your required Windows-only work

### 1. Unpack and source hygiene check

Unpack `CSM_v0_6_1_rc16_LOCAL_SOURCE.zip` into a clean directory.

Run:

```powershell
Get-FileHash .\CSM_v0_6_1_rc16_LOCAL_SOURCE.zip -Algorithm SHA256
Get-ChildItem -Recurse -Force | Where-Object { $_.FullName -match '\\(node_modules|__pycache__|bin|obj|installer\\output)(\\|$)' -or $_.Name -like '*.pyc' }
Select-String -Path .\VERSION.json,.\addin\manifest.xml,.\addin\taskpane.html,.\tools\install-csm.ps1,.\server\redactor.py -Pattern 'rc16|rc15|rc14|rc13|final6|v0.5'
```

Expected:

- no `node_modules`, `__pycache__`, `.pyc`, `bin`, `obj`, or stale `installer/output` artifacts in source,
- active runtime files show rc16,
- no active rc15/rc14/rc13/final6/v0.5 labels in those files except where explicitly negative-tested.

### 2. Python/Node checks on Windows

Run from source root:

```powershell
npm ci
npm run lint --silent
npm run build --silent
py -3.12 -m pip install -r .\server\requirements.txt
py -3.12 -m compileall -q server tests tools
py -3.12 tools\evaluate_pseudonymization_grid.py
py -3.12 -m pytest -q tests\test_release_hygiene.py tests\test_rc16_mapping_grid_and_headings.py tests\test_final_assets_cache_and_mapping_ux.py tests\test_installer_runtime_resilience_rc7.py tests\test_document_profiles_and_mapping_actions.py tests\test_fresh_windows_python_compatibility.py tests\test_installer_resilience_matrix.py tests\selftest.py
```

### 3. .NET sidecar gates

Run:

```powershell
dotnet --info
dotnet restore .\sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
dotnet build .\sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release --no-restore
dotnet test .\sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release --no-restore
```

Then set the compiled sidecar command and run integration tests:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = "$PWD\sidecar\CSM.RevisionSidecar\bin\Release\net8.0\CSM.RevisionSidecar.exe"
py -3.12 -m pytest -q tests\test_revision_sidecar_integration.py tests\test_ci_sidecar_command_release_gate.py
```

Expected: no skipped real-sidecar tests and no failure.

### 4. Build installer EXE

Build a fresh EXE from rc16 source only. Do not reuse any EXE from rc15 or earlier.

```powershell
.\installer\build-csm-setup.ps1
Get-FileHash .\installer\output\CSM-Setup-v0.6.1.exe -Algorithm SHA256
```

Expected:

- `installer/output/CSM-Setup-v0.6.1.exe` exists,
- EXE is freshly built after rc16 source changes,
- build log does not show stale source labels.

### 5. Clean install test

On a clean Windows user profile or VM:

1. Run the generated EXE normally through the GUI, not silent mode only.
2. Confirm the license prompt is not duplicated by hidden PowerShell.
3. Confirm the installer does not hang at the end.
4. Confirm setup log exists at `%TEMP%\CSM-setup-once.log`.
5. Confirm install log exists at `%TEMP%\CSM-install.log` if produced by Inno.
6. Confirm local runtime logs are created under `C:\CSM\logs\`.
7. Confirm `.venv` uses Python 3.12 x64.
8. Confirm imports work inside `.venv`:

```powershell
C:\CSM\server\.venv\Scripts\python.exe -c "import fastapi,uvicorn,pydantic,lxml.etree; print('imports=OK')"
```

### 6. Upgrade/repair after CSM 0.5 final2/final6

Use a real or simulated old 0.5 state. At minimum include stale:

- `C:\CSM` contents,
- old `.venv`,
- old add-in files/cache labels,
- old shortcuts/autostart tasks if applicable,
- old cert files if applicable.

Then run the rc16 EXE.

Expected:

- no installer hang,
- stale `.venv` is removed/recreated if incompatible or incomplete,
- active panel shows rc16,
- active add-in manifest/taskpane cache busters are rc16,
- backend and add-in HTTPS server start,
- old 0.5/final labels are not active in the installed files.

### 7. Certificate and services

Run diagnostics and direct checks:

```powershell
.\tools\diagnose-csm.ps1
Invoke-WebRequest https://localhost:3000/taskpane.html -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:8787/health -UseBasicParsing
```

Expected:

- localhost certificate exists and is trusted in CurrentUser Root,
- diagnostics show `trusted=True` or equivalent positive trust check,
- add-in server responds on 3000 over HTTPS,
- backend responds on 8787.

### 8. Word/WebView smoke test

Open Microsoft Word and verify:

1. CSM add-in loads without Office/WebView blocking.
2. Panel shows `v0.6.1 — rc16`.
3. UI assets load and no broken icons/logo appear.
4. Backend connection is healthy.
5. Pseudonymization runs on a legal text sample.
6. Restore returns the original clear text for mapped values.
7. No visible false positives for headings such as `UMOWA SPRZEDAŻY` or `WEZWANIE DO ZAPŁATY`.
8. Contextual values such as `Powód: OLIMP LABORATORIES`, `Pani Iwony Teresy Ustrzyckiej`, `nr sprawy ABC.123.4.2026`, and `nr rej. RZE 12345` behave according to the mapping grid.

### 9. Package naming rule

If every gate passes, return:

```text
CSM_v0_6_1_rc16_WINDOWS_VERIFIED.zip
CSM-Setup-v0.6.1.exe
CLAUDE_CODE_RC16_WINDOWS_VERIFICATION_REPORT.md
SHA256SUMS.txt
```

If anything fails or remains unverified, return:

```text
CSM_v0_6_1_rc16_WINDOWS_TESTED_WITH_FAILURES.zip
CSM-Setup-v0.6.1.exe, if built
CLAUDE_CODE_RC16_WINDOWS_TESTED_WITH_FAILURES_REPORT.md
SHA256SUMS.txt
```

Do not call it final 0.6.1 unless all gates pass.
