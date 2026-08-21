# CSM 1.4 RC35 — uncertain review modal and reversible pseudonymization check

## Scope

RC35 adds an opt-in, local-only review step for doubtful elements detected after the normal pseudonymization pass.

The change is intentionally conservative: CSM does not automatically mask these uncertain values. The taskpane displays a modal where the user can select which values should be added to manual pseudonymization controls. After confirmation, CSM regenerates a new `_CSM_anon.docx` copy with the selected values included in the local map.

## User-visible change

After creating `_CSM_anon.docx`, if CSM detects doubtful elements, the panel shows a modal:

- values are shown only locally in the Word taskpane;
- every item has a checkbox;
- the user can select all or only selected values;
- selected values are added to `always` manual controls with a suggested category;
- CSM then runs `/v4/current/remask-session` and creates a new `_CSM_anon.docx`;
- the user may skip the review and continue manually.

This is designed for borderline cases where aggressive automatic rules could cause false positives.

## Added backend logic

Added `collect_uncertain_review_candidates()` in `server/redactor.py`.

It suggests local-only candidates from:

- labelled business values such as `Nazwa robocza projektu`, `Kontrahent/nazwa`, `Beneficjent pomocy`, `vendor_id`, `tenant_id`, `login`;
- reverse-address formats such as `39-200 Dębica, Pustynia 84F`;
- descriptive contractor phrases such as `Główny wykonawca to Zielony Dach`;
- project/system names in descriptive prose.

The function excludes already-masked values and does not write raw values into the standard non-disclosing anonymization report.

## Added frontend logic

Added a taskpane modal:

- `uncertainReviewModal`
- `uncertainReviewList`
- `btnUncertainApply`
- `btnUncertainSkip`
- `btnUncertainSelectAll`
- `btnReviewUncertain`

The modal integrates with existing manual-control flow. It does not create a separate restore mechanism and does not change the map/restore architecture.

## Reversibility check

The restore/mapping functions were compared against RC34 by hashing their source definitions.

All checked functions are identical:

- `save_map`
- `load_map`
- `mask_ooxml`
- `restore_ooxml`
- `restore_ooxml_parts`
- `restore_ooxml_package_bytes`
- `_restore_text_value`
- `mask_ooxml_package_bytes`

Detailed hash report: `CSM_RC35_RESTORE_FUNCTION_HASH_CHECK.json`.

## Verification pass 1 — full segmented test suite

Because one monolithic `pytest -q` run exceeded the container timeout near the end, the same suite was run in deterministic file chunks.

Result:

```text
768 passed
3 skipped
0 failed
```

The 3 skipped tests require a compiled real `.NET sidecar` and `CSM_REVISION_SIDECAR_CMD` in a Windows environment.

## Verification pass 2 — critical workflow and UI gates

Second pass:

```text
114 passed
0 failed
```

Included:

- uncertain-review modal tests;
- current workflow tests;
- current restore contract;
- restore state and placeholder retry;
- tracked-change restore preservation;
- manual controls and persistence;
- mapping controls export;
- RC32/RC33/RC34 regression gates;
- taskpane integration;
- frontend/backend UX contract;
- frontend state machine;
- revision frontend sync;
- Word revision engine.

Static validation:

```text
CSM lint validation passed for v1.4.
CSM build validation passed for v1.4.
```

## Known limitation

This container cannot execute the real Windows Word + .NET sidecar integration. The sidecar-specific tests remain skipped here and should be run on the target Windows/Word environment before production rollout.

