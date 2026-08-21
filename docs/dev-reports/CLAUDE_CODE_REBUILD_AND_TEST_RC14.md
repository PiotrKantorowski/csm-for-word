# Claude Code — rebuild and verify CSM v0.6.1 rc14

## Input

Use only:

```text
CSM_v0_6_1_rc14_span_safe_pseudonymization_SOURCE.zip
```

Do not reuse any EXE from rc13 or earlier. rc14 changes pseudonymization code and active labels, so the previous installer is outdated.

## Purpose of rc14

rc14 builds on rc13 and fixes additional Polish legal pseudonymization issues:

1. span-safe masking instead of global literal replacement,
2. title + single surname/name detection, e.g. `Pani Mucha`,
3. uppercase company after `przeciwko`,
4. procedural label preservation, e.g. `Pozwany [COMPANY_1]`,
5. safer locality capture after `siedzibą w`.

Read:

```text
CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md
CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC14_ADDENDUM.md
CSM_RC13_WINDOWS_AUDIT_AND_RC14_SOURCE_REPORT.md
```

## Required build commands

Run from the unpacked source root on Windows:

```powershell
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
py -3.12 -m compileall -q server tests tools
```

Run Python tests:

```powershell
py -3.12 -m pytest -q tests/test_rc13_polish_pseudonymization_rules.py tests/test_rc14_polish_edge_cases.py tests/test_pseudonymization_extended_recommendations.py tests/test_legal_lexicon_contracts_pleadings.py tests/test_rc11_install_privacy_hardening.py tests/test_installer_resilience_matrix.py tests/test_release_hygiene.py tests/test_final_assets_cache_and_mapping_ux.py tests/test_installer_runtime_resilience_rc7.py
```

Run sidecar tests:

```powershell
dotnet restore sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj
dotnet build sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj -c Release --no-restore
dotnet restore sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj
dotnet test sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj -c Release --no-restore
```

Then run integration through the compiled EXE, not `dotnet run`:

```powershell
$env:CSM_REVISION_SIDECAR_CMD = (Resolve-Path "sidecar/CSM.RevisionSidecar/bin/Release/net8.0/CSM.RevisionSidecar.exe").Path
py -3.12 -m pytest -q tests/test_revision_sidecar_integration.py
```

Expected: no skipped real-sidecar tests.

## Build installer

Before building, verify:

```powershell
Select-String -Path addin/taskpane.html,addin/manifest.xml,tools/install-csm.ps1,VERSION.json -Pattern "rc14"
Select-String -Path addin/taskpane.html,addin/manifest.xml,tools/install-csm.ps1,VERSION.json -Pattern "rc11|rc12|rc13|final2|final6|v0.5" | Out-String
```

The second command should not show active runtime labels. Mentions inside historical reports are acceptable, but active files must be rc14.

Build:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer/build-csm-setup.ps1
```

Expected output:

```text
installer/output/CSM-Setup-v0.6.1.exe
```

Record SHA-256:

```powershell
Get-FileHash installer/output/CSM-Setup-v0.6.1.exe -Algorithm SHA256
```

## Manual installer tests — mandatory

### 1. Clean install

On a clean Windows profile/machine:

1. Run `CSM-Setup-v0.6.1.exe` without silent flags.
2. Confirm license screen blocks progress until accepted.
3. Confirm the installer does not hang at the end.
4. Confirm `%TEMP%\CSM-install.log` and `%TEMP%\CSM-setup-once.log` exist.
5. Confirm `C:\CSM\server\.venv\Scripts\python.exe` exists.
6. Confirm `http://127.0.0.1:8787/health` returns version `0.6.1`.
7. Confirm `https://localhost:3000/taskpane.html` loads.
8. Confirm diagnostic shows `trusted=True` for localhost certificate.

### 2. Upgrade/repair from 0.5

On a real or simulated machine with old CSM 0.5/final2/final6 state:

1. old `C:\CSM`,
2. old Office cache,
3. possibly broken `.venv`,
4. old or missing localhost certificate,
5. old Word trusted catalog.

Run rc14 installer and confirm:

1. no GUI hang,
2. `.venv` is rebuilt,
3. dependencies install from wheelhouse,
4. old cache is cleared,
5. panel shows rc14, not 0.5/final2/final6,
6. `/health` returns 0.6.1,
7. Word loads the add-in.

### 3. Word/WebView

Open Microsoft Word and verify:

1. CSM panel opens without blocked-add-in warning,
2. taskpane shows `v0.6.1 — rc14`,
3. technical status loads,
4. pseudonymization runs on a real DOCX,
5. restore returns the document to the original content,
6. tracked changes are preserved when sidecar is enabled.

## Pseudonymization manual tests

Test at least these strings and one real DOCX:

```text
Pani Mucha złożyła wniosek. Mucha była widoczna w salonie.
Powód Jan Nowak wnosi pozew przeciwko OLIMP LABORATORIES.
Pozwany Mucha sp. z o.o. z siedzibą w Pustyni wnosi odpowiedź.
na rzecz Pani Iwony Teresy Ustrzyckiej (PESEL: 90010112345)
Anna Pustynia zamieszkała w Pustyni 84F, 39-200 Dębica.
Rachunek bankowy Jana Nowaka: PL 12 3456 7890 1234 5678 9012 3456.
```

For every case, verify:

1. sensitive entity is masked,
2. ordinary non-sensitive occurrence is not over-masked,
3. restore returns exactly the original string,
4. map/backup is protected as designed.

## DoD for rc14

Do not call this final unless all are true:

- clean install PASS,
- upgrade/repair after 0.5 PASS,
- Word/WebView PASS,
- sidecar EXE integration PASS with zero skipped real-sidecar tests,
- pseudonymization manual tests PASS,
- restore exactness PASS,
- no GUI installer hang,
- no active rc11/rc12/rc13/final2/final6/v0.5 labels,
- final ZIP contains EXE, wheelhouse, reports and no cache/build junk.

## Return package naming

If all manual tests pass:

```text
CSM_v0_6_1_rc14_WINDOWS_VERIFIED.zip
```

If any mandatory manual test is not completed or fails:

```text
CSM_v0_6_1_rc14_WINDOWS_TESTED_WITH_FAILURES.zip
```

Include a report with exact commands, results, SHA-256 of source ZIP and EXE, and screenshots/log excerpts for GUI/Word tests.
