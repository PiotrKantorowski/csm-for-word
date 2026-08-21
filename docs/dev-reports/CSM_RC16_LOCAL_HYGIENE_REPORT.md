# CSM v0.6.1 rc16 — local hygiene iteration report

Date: 2026-05-19
Input baseline: `CSM_v0_6_1_rc15_LOCAL_SOURCE.zip`
Output source package: `CSM_v0_6_1_rc16_LOCAL_SOURCE.zip`
Status: source candidate only; not final 0.6.1.

## Scope of this local iteration

This iteration deliberately covers only work that can be verified in this Linux/container environment. It does not claim Windows, Word, WebView, Inno Setup, certificate trust, or real .NET sidecar verification.

## Changes made locally

### 1. Active asset hygiene

The rc15 add-in manifest and taskpane used current cache busters but still referenced assets whose filenames contained `final6`, for example:

- `icon-32-csm-final6.png?build=20260519-rc15`
- `logo-csm-primary-final6.png?build=20260519-rc15`

For rc16, current active assets were copied to version-neutral current-candidate names and all active references were updated:

- `addin/icon-16-csm-rc16.png`
- `addin/icon-32-csm-rc16.png`
- `addin/icon-64-csm-rc16.png`
- `addin/icon-80-csm-rc16.png`
- `assets/logo-csm-primary-rc16.png`

Active manifest/taskpane references now use `rc16` asset names and `20260519-rc16` cache busters.

### 2. Release notes hygiene

`RELEASE-NOTES-v0.6.1.txt` no longer contains a visible `Poprawka rc7` section or `v0.5.0` wording in the active release-notes copy. This reduces the risk that a tester or Claude Code treats old internal candidate labels as current release information.

### 3. Source comments hygiene

Historical implementation comments in `server/tc_engine.py` were rewritten to avoid old labels such as `final3`, `final4`, and `v0.5 final5`. The comments now describe the behavior generically:

- range-wide logic,
- value-after-restore matching,
- context-aware restore path.

### 4. Version bump to rc16

Active labels were updated from rc15 to rc16 in:

- `VERSION.json`,
- `addin/manifest.xml`,
- `addin/taskpane.html`,
- `tools/install-csm.ps1`,
- `server/redactor.py`,
- tests that assert active labels.

Current active markers:

- build: `v0.6.1-rc16-local-hygiene-20260519`,
- engine version: `0.2.45-rc16-local-hygiene`,
- Word panel badge: `v0.6.1 — rc16`,
- add-in cache busters: `20260519-rc16` and `0.6.1-rc16-20260519`.

### 5. Test naming hygiene

The rc15 mapping-grid test file was renamed to:

- `tests/test_rc16_mapping_grid_and_headings.py`

The mapping grid document was updated to `rc16 local hygiene draft`.

### 6. Superseded rc15 local files removed from source root

Removed from the working source because they are superseded by rc16:

- `CLAUDE_CODE_RC15_WINDOWS_ONLY_HANDOFF.md`,
- `CSM_RC15_LOCAL_ITERATION_REPORT.md`,
- rc15-only copied asset files.

This does not remove older historical project reports that were already part of the source history, but it prevents the immediately previous local handoff from being mistaken for the current one.

## Local validation performed

### Python / pytest

Tests were run in chunks because a single full `pytest -q` invocation can exceed the execution timeout in this environment.

Result by file chunks:

```text
pytest files 1-20: 86 passed
pytest files 21-40: 112 passed
pytest files 41-60: 109 passed
pytest files 61-62: 9 passed, 3 skipped
pytest files 63-65: 11 passed
pytest files 66-79: 60 passed
```

Total from chunked run:

```text
387 passed, 3 skipped
```

The 3 skipped tests are expected here because `CSM_REVISION_SIDECAR_CMD` is not set and the real compiled .NET sidecar executable is not available in this environment.

Additional targeted validation after final documentation edits:

```text
tests/test_release_hygiene.py tests/test_rc16_mapping_grid_and_headings.py: 25 passed
```

### Mapping grid evaluator

```text
Cases: 16
PASS: 16
FAIL_FALSE_NEGATIVE: 0
FAIL_FALSE_POSITIVE: 0
FAIL_WRONG_CATEGORY: 0
RESTORE_FAIL: 0
AMBIGUOUS_WARNING: 0
```

### Node/add-in checks

```text
npm run lint --silent: PASS
npm run build --silent: PASS
node --check addin/revision_bridge.js: PASS
node --check addin/taskpane.js: PASS
node --check addin/scripts/validate-static.js: PASS
```

### Python compile check

```text
python3 -m compileall -q server tests tools: PASS
```

Generated `__pycache__` and `.pyc` files were removed before packaging.

### Active-label grep

The active runtime/documentation set was checked for old candidate labels using:

```text
VERSION.json
README*.md
RELEASE-NOTES-v0.6.1.txt
install-guide.html
ZAINSTALUJ_CSM.cmd
addin/
server/
installer/
tools/
.github/
docs/PSEUDONYMIZATION_MAPPING_GRID.md
```

No active `rc1-rc15`, `finalN`, `v0.5`, or `20260516-final6` labels remained in that checked active set.

## Not verified locally

The following remain mandatory for Claude Code / Windows:

1. Inno Setup EXE build.
2. Clean Windows install.
3. Upgrade/repair after real or simulated CSM 0.5 final2/final6 state.
4. GUI installer non-silent test.
5. Windows certificate trust: `trusted=True` in CurrentUser Root.
6. Backend on 8787 and add-in HTTPS server on 3000.
7. Microsoft Word/WebView add-in load and functional UI test.
8. `dotnet restore`, `dotnet build`, `dotnet test` for sidecar projects.
9. Python -> compiled real sidecar EXE integration tests by setting `CSM_REVISION_SIDECAR_CMD`.
10. Real Word pseudonymize -> restore smoke test.

## Recommendation

Do not send broad development instructions to Claude Code. Send only:

1. `CSM_v0_6_1_rc16_LOCAL_SOURCE.zip`,
2. `CLAUDE_CODE_RC16_WINDOWS_ONLY_HANDOFF.md`,
3. optionally this report and SHA-256 file.

Claude Code should be treated as the Windows/Word/Inno/.NET verification worker, not as the general maintainer for this iteration.
