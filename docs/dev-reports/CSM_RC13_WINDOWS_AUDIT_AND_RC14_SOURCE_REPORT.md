# CSM v0.6.1 rc13 Windows package audit and rc14 source changes

## Input audited

Package: `CSM_v0_6_1_rc13_WINDOWS_TESTED_WITH_FAILURES.zip`

Actual SHA-256:

```text
9d740fe26c0a6943ecc9b84a64e4d026ed585621ec676331000dc5ebb53d9f29
```

Installer EXE found in package:

```text
installer/output/CSM-Setup-v0.6.1.exe
```

Actual EXE SHA-256:

```text
ac174ac154a7a565ac21e1200de6382e3f827300d0e127f63bfb4cfa48cdadc3
```

## What Claude Code confirmed

Claude Code made meaningful progress compared with earlier packages:

- `npm run lint`, `npm run build`, Node syntax checks and Python compileall passed.
- .NET 8 restore/build/test passed.
- Real sidecar integration through compiled `CSM.RevisionSidecar.exe` passed 8/8.
- Windows wheelhouse exists and contains runtime wheels for Python 3.12 x64.
- Inno Setup produced `CSM-Setup-v0.6.1.exe`.
- Active labels were updated to rc13 in the reported build.

## What remains unconfirmed

The package name correctly includes `WITH_FAILURES`. The following blockers were not manually confirmed:

1. GUI installer without silent flags.
2. Upgrade/repair from a real CSM 0.5 final2/final6 installation.
3. Microsoft Word/WebView interactive test.
4. Full tracked-changes sidecar result opened and visually checked in Word.
5. Full reversible pseudonymization/restore on representative Polish legal documents in Word.

## Additional issues found during audit

While auditing the rc13 package, additional Polish pseudonymization edge cases were found:

1. `Pani Mucha złożyła wniosek` was not masked, because the engine required a multi-token person name.
2. `Powód Jan Nowak wnosi pozew przeciwko OLIMP LABORATORIES` did not mask the uppercase defendant company after `przeciwko`.
3. `Pozwany Mucha sp. z o.o.` could swallow the procedural role label into the company replacement.
4. The previous global replacement strategy could over-mask ordinary words when a surname was also an ordinary Polish word, e.g. after detecting `Pani Mucha`, a bare unrelated `Mucha` in another sentence could also be replaced.
5. `siedzibą w Pustyni wnosi...` could over-capture following lowercase prose as part of the locality in some contexts.

## Changes made in rc14 source

### 1. Span-safe replacement

`make_replacements_with_controls` now replaces only accepted detection spans instead of using global `str.replace()` for every original value.

This reduces false positives for ambiguous Polish words such as:

- `Mucha`,
- `Pustynia`,
- other surnames/place names that may also be common words.

Repeated aliases are still masked when they are explicitly added as findings by contextual alias detectors.

### 2. Title + single surname/name detection

Added a title-anchored person detector for cases such as:

```text
Pani Mucha
Pan Pustynia
```

The detector is context-limited and does not mask a bare ordinary occurrence elsewhere.

### 3. Company after `przeciwko`

Added a separate detector for uppercase company names after the procedural phrase `przeciwko`, so:

```text
Powód Jan Nowak wnosi pozew przeciwko OLIMP LABORATORIES.
```

masks both the person and the uppercase defendant company.

### 4. Party label trimming

Fixed role-label trimming so:

```text
Pozwany Mucha sp. z o.o.
```

becomes:

```text
Pozwany [COMPANY_1]
```

instead of replacing the role label together with the company.

### 5. Address locality capture hardening

`ADDRESS_SIEDZIBA` was changed so the locality capture is case-sensitive while the preceding phrase remains case-insensitive. This prevents accidental capture of following lowercase prose.

## Tests run in this environment

Passed:

```text
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
python3 -m compileall -q server tests tools
```

Targeted pytest:

```text
tests/test_rc13_polish_pseudonymization_rules.py
tests/test_rc14_polish_edge_cases.py
tests/test_pseudonymization_extended_recommendations.py
tests/test_legal_lexicon_contracts_pleadings.py
tests/test_rc11_install_privacy_hardening.py
tests/test_installer_resilience_matrix.py
tests/test_release_hygiene.py
tests/test_final_assets_cache_and_mapping_ux.py
tests/test_installer_runtime_resilience_rc7.py
```

Result:

```text
54 passed
```

Sidecar/frontend contract tests:

```text
19 passed, 3 skipped
```

The skipped tests require `CSM_REVISION_SIDECAR_CMD` pointing to a compiled sidecar executable.

Full `pytest -q` reached about 75% without visible failures, but the current environment timed out before completion.

## Output status

Prepared source package:

```text
CSM_v0_6_1_rc14_span_safe_pseudonymization_SOURCE.zip
```

This is a source package without EXE. The rc13 EXE is now outdated and must not be reused.
