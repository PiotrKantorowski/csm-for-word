# CSM Iter 18 — RC8: Install Profile Fix + Common-Word Anonymization Fixes

**Version:** CSM v0.6.1 rc8  
**Date:** 2026-05-18  
**Base:** rc7 FINAL

---

## Summary

RC8 addresses three issues discovered after rc7 field testing:

1. **Installer hang near the end** — `setup-once.ps1` was prompting for license acceptance (`AKCEPTUJE`) in a hidden child process when launched from the GUI installer, making the setup appear frozen.

2. **User-profile setup in wrong profile** — The Inno Setup `[Run]` step did not use `runasoriginaluser`, so the user-profile phase (certificates, shortcuts, autostart) could accidentally run in an elevated/admin profile instead of the real user profile.

3. **Anonymization false negatives for common words** — Three categories of ordinary Polish words used as surnames or locality names were not anonymized:
   - **Mucha** (Polish for "fly") as a surname: `Renata Mucha`, `Patryk Kowalski` (first names not in lexicon)
   - **Pustynia** (Polish for "desert") as a village name in address: `Pustynia 84F, 39-200 Dębica`
   - **Meble New Concept** as a company brand name: only `Concept Sp. z o.o.` was matched; `Meble New` was stripped as a fake person prefix

---

## Changes

### 1. `tools/setup-once.ps1` — FromInstaller switch

Added `[switch]$FromInstaller` parameter. The license-acceptance block now distinguishes three cases:

```powershell
if (Test-Path $LicenseAccepted) {
    Write-Info "Licencja byla juz zaakceptowana." Green
} elseif ($FromInstaller) {
    Set-Content -Path $LicenseAccepted -Value ("accepted_at=" + ...) -Encoding UTF8
    Write-Info "Licencja zaakceptowana w oknie instalatora." Green
} else {
    Require-LicenseAcceptance
}
```

When the switch is set, the license marker is written silently without any interactive prompt.

### 2. `installer/CSM-Setup.iss` — runasoriginaluser

Added `runasoriginaluser` to the `[Run]` Flags:

```
Flags: runhidden waituntilterminated runasoriginaluser
```

### 3. `tools/install-csm.ps1` — -FromInstaller propagation

`Run-SetupOnce` already passes `-FromInstaller` when `$OriginalSourceRoot` is non-empty (i.e. launched from the GUI installer). This was in place from the rc7 iteration; confirmed working.

### 4. `server/legal_lexicon.py` — first names added

Added common Polish first names missing from `COMMON_POLISH_FIRST_NAMES`:

```python
COMMON_POLISH_FIRST_NAMES.update({
    "RENATA", "PATRYK", "IWONA", "TERESA", "HENRYK", "CELINA", "WALDEMAR",
    "TADEUSZ", "STANISŁAW", "STANISLAW", "RYSZARD", "MIROSŁAW", "MIROSLAW",
    "WŁADYSŁAW", "WLADYSLAW", "KRYSTYNA", "ELŻBIETA", "ELZBIETA", "HALINA",
    "GRAŻYNA", "GRAZYNA", "BOŻENA", "BOZENA", "WIESŁAW", "WIESLAW",
    "ZENON", "LECH", "MAREK", "ZYGMUNT", "ROMAN", "LEON", "ARNOLD",
})
```

### 5. `server/redactor.py` — ADDRESS_RURAL pattern

Added new `ADDRESS_RURAL` pattern to `PATTERNS`:

```python
"ADDRESS_RURAL": re.compile(rf"\b{CITY_WORD}(?:\s+{CITY_WORD}){{0,2}}\s+{BUILDING_NUMBER}\s*,\s*\d{{2}}-\d{{3}}\s+{CITY_NAME}\b"),
```

Matches village-format addresses without a street prefix (e.g. `Pustynia 84F, 39-200 Dębica`).

### 6. `server/redactor.py` — ADDRESS_SIEDZIBA pattern

Added new `ADDRESS_SIEDZIBA` pattern:

```python
"ADDRESS_SIEDZIBA": re.compile(rf"(?i)\bsiedzib[aąę]\s+w\s+(?P<id>{CITY_WORD}(?:\s+{CITY_WORD}){{0,2}})(?=\s*,|\s*[.;)]|\s+{BUILDING_NUMBER}|$)"),
```

Extracts the locality name from `z siedzibą w Pustyni` and masks it.

### 7. `server/redactor.py` — _trim_leading_person_from_company fix

The trim function that strips accidental person-name prefixes from company matches now requires `_looks_like_person_name()` to return True before stripping:

```python
# Before (buggy):
if m and valid_tail(m.group(2).strip()):

# After (fixed):
if m and valid_tail(m.group(2).strip()) and _looks_like_person_name(m.group(1)):
```

This prevents `Meble New` from being trimmed as a pseudo person name.

---

## Test file created

`tests/test_rc8_install_and_common_word_regressions.py` — 14 tests covering all rc8 DoD scenarios.

---

## Before / After

### Mucha surname

| Input | Before | After |
|-------|--------|-------|
| `Renata Mucha, PESEL: 12345678902` | `Renata [PERSON_1_ALIAS_1], PESEL: [PESEL_2]` | `[PERSON_2], PESEL: [PESEL_2]` |
| `Jan Mucha. Mucha jest zobowiązany...` | `[PERSON_1]. [PERSON_1_ALIAS_1] jest...` | `[PERSON_1]. [PERSON_1_ALIAS_1] jest...` |

### Pustynia address

| Input | Before | After |
|-------|--------|-------|
| `Pustynia 84F, 39-200 Dębica` | `Pustynia 84F, [POSTCODE_PL_1] Dębica` | `[ADDRESS_RURAL_1]` |
| `z siedzibą w Pustyni, Pustynia 84F, 39-200 Dębica` | `z siedzibą w Pustyni, Pustynia 84F, [POSTCODE_PL_1] Dębica` | `z siedzibą w [ADDRESS_SIEDZIBA_1], [ADDRESS_RURAL_1]` |

### Meble New Concept

| Input | Before | After |
|-------|--------|-------|
| `Meble New Concept Sp. z o.o.` | `Meble New [COMPANY_1]` | `[COMPANY_1]` |
