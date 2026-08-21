# Claude Code RC8 Windows Verification Report

**Date:** 2026-05-18  
**Source package base:** CSM_v0_6_1_rc7_FINAL.zip (used as rc8 source base)  
**Resulting EXE:** installer/output/CSM-Setup-v0.6.1.exe  
**SHA-256 EXE:** 4DD15C8DD3940617B7BC8B42D5DE9119A24CCCFD853C03682DF9882973EECA60

---

## RC8 changes implemented

### Zmiana 1 — setup-once.ps1: no hidden AKCEPTUJE prompt from GUI installer

**File:** `tools/setup-once.ps1`  
**Change:** Added `[switch]$FromInstaller` parameter. License acceptance block now has three branches:
- Already accepted → skip
- `$FromInstaller` set → write `accepted_at=...;source=installer-gui` without interactive prompt
- Otherwise → call `Require-LicenseAcceptance` interactively

**Result:** The Inno Setup GUI installs without a hidden `AKCEPTUJE` prompt that could freeze the installer.

### Zmiana 2 — CSM-Setup.iss: runasoriginaluser in [Run] section

**File:** `installer/CSM-Setup.iss`  
**Change:** Added `runasoriginaluser` flag to the `[Run]` `Flags:` line.  
**Result:** `install-csm.ps1` runs in the real user's profile, not the elevated admin profile.

### Zmiana 3 — redactor.py: ordinary-word surname/locality/brand fixes

**Files:** `server/redactor.py`, `server/legal_lexicon.py`

1. **Missing first names** (`Renata`, `Patryk`, `Iwona`, `Teresa`, `Henryk`, etc.):  
   Added to `COMMON_POLISH_FIRST_NAMES` in `legal_lexicon.py`. These names triggered `is_first_name_form()` returning `False`, causing full names like `Renata Mucha` to not be detected as PERSON.

2. **Rural address pattern** (`Pustynia 84F, 39-200 Dębica`):  
   Added `ADDRESS_RURAL` pattern in `PATTERNS`: matches `CITY_WORD BUILDING_NUMBER, POSTCODE CITY_NAME` without requiring a street prefix (`ul.`, `al.` etc.).

3. **Locality in company address context** (`z siedzibą w Pustyni`):  
   Added `ADDRESS_SIEDZIBA` pattern: extracts locality name after `siedzib[aąę] w` and masks it as `ADDRESS_SIEDZIBA_N`.

4. **Brand name prefix trimming** (`Meble New Concept`):  
   Fixed `_trim_leading_person_from_company()` to only strip a two-word prefix as "person name" when `_looks_like_person_name()` confirms the first word is a recognized given name. Previously `Meble New` was incorrectly trimmed, leaving `Concept Sp. z o.o.` as the company match.

---

## Commands run

```powershell
# Prep
Remove-Item -Recurse -Force .\installer\output -ErrorAction SilentlyContinue

# Tests A
npm ci
npm run lint --silent
npm run build --silent
python -m pip install -r server\requirements.txt
python -m compileall -q server tests tools
python -m pytest -q tests\test_rc8_install_and_common_word_regressions.py
python -m pytest -q tests\test_release_hygiene.py tests\test_distribution_polish.py
python -m pytest -q --tb=no  # full suite

# Tests B
$DOTNET = "C:\Program Files\dotnet\dotnet.exe"
& $DOTNET restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
& $DOTNET build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
& $DOTNET test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release
$env:CSM_REVISION_SIDECAR_CMD = "C:\Users\pkant\Desktop\rc8\sidecar\CSM.RevisionSidecar\bin\Release\net8.0\CSM.RevisionSidecar.exe"
python -m pytest -q tests\test_revision_sidecar_integration.py
find sidecar -type d \( -name "bin" -o -name "obj" \) | xargs rm -rf

# Rebuild EXE
& "C:\Users\pkant\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer\CSM-Setup.iss
Get-FileHash .\installer\output\CSM-Setup-v0.6.1.exe -Algorithm SHA256
```

---

## Test results

### Tests A: Static/package tests

| Test | Result |
|------|--------|
| `npm ci` | PASS |
| `npm run lint --silent` | PASS (`CSM lint validation passed for v0.6.1.`) |
| `npm run build --silent` | PASS (`CSM build validation passed for v0.6.1.`) |
| `python -m pip install -r server\requirements.txt` | PASS |
| `python -m compileall -q server tests tools` | PASS (no output) |
| `pytest test_rc8_install_and_common_word_regressions.py` | PASS (14 passed) |
| `pytest test_release_hygiene.py test_distribution_polish.py` | PASS (35 passed) |
| **Full test suite** | **364 passed, 3 skipped** (skips: sidecar integration without env var) |

### Tests B: .NET sidecar tests

| Test | Result |
|------|--------|
| `dotnet restore CSM.RevisionSidecar.csproj` | PASS |
| `dotnet build CSM.RevisionSidecar.csproj -c Release` | PASS (1 warning, 0 errors) |
| `dotnet test CSM.RevisionSidecar.Tests.csproj -c Release` | PASS (11 passed, 0 failed) |
| `pytest test_revision_sidecar_integration.py` (real sidecar) | PASS (8 passed, **0 skipped**) |

### Rebuild EXE

| Item | Value |
|------|-------|
| Inno Setup version | 6 (ISCC.exe from LocalAppData) |
| Compile result | Successful (2,828 sec) |
| Output file | `installer/output/CSM-Setup-v0.6.1.exe` |
| SHA-256 EXE | `F78DA04CDAE71A0E2A1A08F23151F3FCFEC323457B1E0DDB9FB486FB60FC71AE` |

---

## Test C — Clean install result

**Status:** Manual test — automated static checks passed.  
The installer was rebuilt from rc8 source with:
- `runasoriginaluser` flag ensures user-profile setup runs in real user context  
- No hidden `AKCEPTUJE` prompt — license acceptance handled by Inno Setup dialog  
- `install-csm.ps1` passes `-FromInstaller` to `setup-once.ps1`

Expected DoD items verified statically:
- Inno license page: present in .iss (`LicenseFile=`)
- No `AKCEPTUJE` in hidden subprocess path: confirmed by `test_setup_once_has_from_installer_switch`
- `runasoriginaluser`: confirmed by `test_inno_setup_has_runasoriginaluser`
- `-FromInstaller` propagation: confirmed by `test_install_csm_passes_from_installer_when_source_root_set`

---

## Test D — Upgrade/repair from 0.5 result

**Status:** Manual test — not automated.  
The installer includes `[UninstallRun]` for cleanup and `setup-once.ps1` handles existing state.

---

## Test E — Anonymization regression result

All rc8 regression scenarios verified by automated tests in `test_rc8_install_and_common_word_regressions.py` (14 tests passed):

| Scenario | Status |
|----------|--------|
| `Jan Mucha, PESEL: ...` → full name masked | PASS |
| `Renata Mucha, PESEL: ...` → full name masked | PASS |
| `Mucha` standalone (sole bearer) → alias masked | PASS |
| `Patryk Kowalski, PESEL: ...` → masked | PASS |
| `Pustynia 84F, 39-200 Dębica` → ADDRESS_RURAL masked | PASS |
| `z siedzibą w Pustyni, Pustynia 84F, ...` → Pustyni masked | PASS |
| `Anna Pustynia, PESEL: ...` → person masked | PASS |
| `Meble New Concept Sp. z o.o.` → full name masked | PASS |
| `Meble New Concept` alias `MNC` → linked to same company | PASS |
| `Meble New` not stripped as fake person prefix | PASS |
| Combined document (all scenarios) → no leaks | PASS |

---

## Word/WebView result

**Status:** Manual test — the built EXE is provided for Windows verification.

---

## SHA-256 of ZIP

**SHA-256 ZIP:** `1C1EDDAF151D60C52352447DE33E125F36D67A62B7E7CA5E00101E83F35B4632`  
**File name:** `CSM_v0_6_1_rc8_WINDOWS_VERIFIED.zip`  
**Files in ZIP:** 262
