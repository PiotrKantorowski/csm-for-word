# CSM rc8 Windows package audit and rc9 source fix

## Scope
Audited uploaded package: `CSM_v0_6_1_rc8_WINDOWS_VERIFIED.zip`.

## Findings from uploaded rc8 package

1. ZIP integrity: OK.
2. Release hygiene: OK — no `node_modules`, `bin`, `obj`, `__pycache__`, `.pyc`, `.pytest_cache` in the uploaded ZIP.
3. Installer artifact present: `installer/output/CSM-Setup-v0.6.1.exe` existed in uploaded rc8 package.
4. `.NET` target: OK — active sidecar projects use `net8.0`.
5. Inno Setup license: OK — `LicenseFile={#SourceDir}\LICENSE.txt` is present.
6. Hidden license prompt fix: OK — `setup-once.ps1` has `-FromInstaller` branch and does not call `Require-LicenseAcceptance` in the hidden installer path.
7. User-profile execution: OK — Inno `[Run]` entry uses `runasoriginaluser`.
8. Audit inconsistency: the Windows verification report contains conflicting hashes:
   - actual uploaded ZIP SHA-256: `119dea5f4e269a228273fbeea5ee1731afc9a9fcd46918226b10990735ae9e90`
   - report states ZIP SHA-256: `1C1EDDAF151D60C52352447DE33E125F36D67A62B7E7CA5E00101E83F35B4632`
   - actual EXE SHA-256: `4dd15c8dd3940617b7bc8b42d5de9119a24cccfd853c03682df9882973eeca60`
   - report header states EXE SHA-256 matching actual EXE, but later rebuild table states a different EXE SHA-256: `F78DA04CDAE71A0E2A1A08F23151F3FCFEC323457B1E0DDB9FB486FB60FC71AE`.
9. Verification status is overstated by package name: the report says clean install and upgrade/repair were not fully automated, and Word/WebView result was not confirmed as a completed manual pass.
10. Active user-facing version label issue: `tools/install-csm.ps1` still printed `CSM v0.6.1 rc7`, and add-in cache busters/badge still used `rc7`.
11. Anonymization gap found during local verification: `Pani Iwony Teresy Ustrzyckiej (PESEL: ...)` left the name visible because title-context person detection did not allow `(` before `PESEL`.

## Fixes applied in rc9 source package

1. Updated active rc labels/cache busters from `rc7` to `rc9` in:
   - `tools/install-csm.ps1`
   - `addin/manifest.xml`
   - `addin/taskpane.html`
   - related tests.
2. Updated `VERSION.json` build marker to `v0.6.1-rc9-install-anonymization-polish-20260518`.
3. Fixed `PERSON_TITLE_CONTEXT_PATTERN` to handle title-context names before parenthesized identifiers, e.g. `Pani Iwony Teresy Ustrzyckiej (PESEL: ...)`.
4. Added regression test:
   - `test_pani_iwony_teresy_ustrzyckiej_with_pesel_parenthesis_is_masked`.
5. Removed stale `installer/output/CSM-Setup-v0.6.1.exe` from the rc9 source package. It must be rebuilt on Windows after these changes.

## Local tests performed after rc9 fixes

Passed:

```text
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
python3 -m compileall -q server tests tools
PYTHONPATH=server python3 -m pytest -q tests/test_rc8_install_and_common_word_regressions.py tests/test_release_hygiene.py tests/test_distribution_polish.py tests/test_installer_runtime_resilience_rc7.py tests/test_final_assets_cache_and_mapping_ux.py tests/test_document_profiles_and_mapping_actions.py
```

Result of the pytest group: `49 passed`.

Manual sample check after patch:

```text
Input:  na rzecz Pani Iwony Teresy Ustrzyckiej (PESEL: 90010112345)
Output: na rzecz Pani [PERSON_1] (PESEL: [PESEL_1])
```

## Not verified in this environment

The following still require Windows / Claude Code / Word runtime:

1. Rebuild `installer/output/CSM-Setup-v0.6.1.exe` from rc9 source.
2. Confirm new EXE SHA-256 and include it in a fresh verification report.
3. Clean install on a fresh Windows user profile.
4. Upgrade/repair install over CSM 0.5.
5. Confirm installer does not freeze at the final progress bar.
6. Confirm `localhost` certificate is trusted.
7. Confirm backend `http://127.0.0.1:8787/health` returns version `0.6.1`.
8. Confirm add-in loads in Word without the blocked-content/add-in certificate warning.
9. Confirm anonymization in Word on real documents containing:
   - Mucha as surname,
   - Pustynia as locality/person surname,
   - Meble New Concept as company,
   - Iwony Teresy Ustrzyckiej before parenthesized PESEL.
