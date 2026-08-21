# CSM rc12 Windows-tested package audit and rc13 source update

## Audited package

`CSM_v0_6_1_rc12_WINDOWS_TESTED_WITH_FAILURES.zip`

## Result

The package is a meaningful step forward because it includes:

- rebuilt installer EXE,
- local Windows wheelhouse,
- .NET 8 sidecar build and tests in the Claude Code report,
- Python-to-sidecar integration through the compiled sidecar EXE,
- rc12 active Word add-in labels.

It is not final 0.6.1 because the Claude Code report still marks the following as unconfirmed:

- interactive GUI installer observation,
- true upgrade/repair from CSM 0.5 final2/final6,
- Word/WebView runtime without add-in block,
- full tracked-changes workflow in Word.

## Issues found during local audit

1. `npm run lint` failed because the ZIP contained generated backup folders under `backups/`.
2. Active installer script still displayed `CSM v0.6.1 rc11 - instalacja jednym plikiem`.
3. The pseudonymization engine classified `Powód Jan Nowak` as `CONTRACTOR/COMPANY` instead of `PERSON`.
4. A bank account after an owner's name, e.g. `Rachunek bankowy Jana Nowaka: PL ...`, was not masked when the number was a fictional test number.
5. A residence locality without street, e.g. `zamieszkały w Pustyni`, was not masked.

## Fixes applied in rc13 source

1. Removed generated backup folders from `backups/`.
2. Updated active labels/cache-busters/install script from rc12/rc11 to rc13.
3. Added Polish pseudonymization rulebook: `CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md`.
4. Added Claude Code instructions: `CLAUDE_CODE_REBUILD_AND_TEST_RC13.md`.
5. Added `tests/test_rc13_polish_pseudonymization_rules.py`.
6. Changed party-context company detection so natural persons introduced by `Powód/Pozwany` are not converted into companies.
7. Added bank-account detection through owner-name context.
8. Added residence-locality detection for phrases such as `zamieszkały w Pustyni`.

## Local tests

Passed locally:

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
51 passed
```

Sidecar/frontend status tests:

```text
tests/test_revision_sidecar_integration.py
tests/test_revision_sidecar_contract.py
tests/test_revision_sidecar_frontend_sync.py
```

Result:

```text
19 passed, 3 skipped
```

The 3 skipped tests require a compiled real .NET sidecar and `CSM_REVISION_SIDECAR_CMD`.

## Packaging note

The rc13 ZIP is a source package without an EXE. Claude Code must rebuild `CSM-Setup-v0.6.1.exe`; the rc12 EXE is stale.
