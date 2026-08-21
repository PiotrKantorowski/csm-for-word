# CSM v0.6.1 rc10 — install and reversible pseudonymization hardening

## Goal
Bring CSM closer to a release-quality 0.6 by hardening two critical areas:

1. installation on different Windows machines without silent hangs or unclear failures;
2. reversible pseudonymization for legal documents where names, locations, and company names may also be ordinary words.

This is a source package. Any previously built `CSM-Setup-v0.6.1.exe` is stale and must be rebuilt from this source.

## Main changes

### Installer / setup reliability

- Added a watchdog wrapper in `tools/install-csm.ps1` for child PowerShell stages.
- `setup-once.ps1` is now executed with a hard timeout of 1800 seconds.
- `start-claude-safe-mode.ps1` is now executed from the installer with a hard timeout of 120 seconds.
- Child output is captured and appended to the main install log, instead of disappearing behind the Inno Setup progress screen.
- `tools/setup-once.ps1` now writes a dedicated log to `%TEMP%\CSM-setup-once.log`.
- Native commands in `setup-once.ps1`, including `pip`, are executed with timeout-aware process handling. Pip warnings on stderr are no longer treated as failure if the process exits successfully.
- The installer error path now points to both `CSM-install.log` and `CSM-setup-once.log`.

### Pseudonymization / reversibility

- Added a context-anchored detector for legal/process party company names without explicit legal suffix, for example:
  - `w imieniu Klienta – OLIMP LABORATORIES`,
  - `Powód: "OLIMP LABORATORIES" z siedzibą ...`.
- Kept a guard against masking generic legal headings such as `WEZWANIE DO ZAPŁATY – OSTATECZNE PRZEDSĄDOWE`.
- Added plain-text reversibility tests: anonymize -> restore using the generated replacement map -> exact original text.
- Tested the previously problematic anonymized notarial document locally: leaked values such as `Mucha`, `Renata Mucha`, and `Iwony Teresy Ustrzyckiej` were masked by the rc10 source engine.

### Release labels

- Active add-in cache busters and visible panel badge were updated from rc9 to rc10.
- `VERSION.json` build marker was updated to `v0.6.1-rc10-install-reversibility-hardening-20260518`.

## Tests run locally

Passed:

```text
npm run lint --silent
npm run build --silent
node --check addin/revision_bridge.js
node --check addin/taskpane.js
node --check addin/scripts/validate-static.js
python3 -m compileall -q server tests tools
```

Targeted pytest groups:

```text
tests/test_rc10_install_and_reversibility_hardening.py: 4 passed
installer / release / rc8 regressions / restore smoke group: 65 passed
current workflow / restore / frontend-backend / revision contract group: 160 passed
revision sidecar integration: 5 passed, 3 skipped
```

The skipped integration tests require a compiled real .NET sidecar and `CSM_REVISION_SIDECAR_CMD`.

A larger combined pytest run reached about 85% before the execution environment timed out, without reporting failures before the timeout.

## Not confirmed in this environment

- `dotnet restore`
- `dotnet build`
- `dotnet test`
- rebuilt Inno Setup EXE
- clean Windows install
- upgrade/repair after 0.5
- Word/WebView runtime
- sidecar E2E through `CSM_REVISION_SIDECAR_CMD`

## Release decision

This should be treated as:

```text
CSM v0.6.1-rc10 source
```

It is not final 0.6 until the Windows/Word/installer tests pass on a real machine and the final EXE is rebuilt from this exact source.
