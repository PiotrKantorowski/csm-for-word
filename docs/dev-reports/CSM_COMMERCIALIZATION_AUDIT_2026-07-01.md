# CSM commercialization audit - 2026-07-01

## Executive status

CSM v1.3 is technically in a strong pre-commercial state: core pseudonymization gates pass, full Python regression suite passes, .NET sidecar tests pass, bundled gazetteer licenses pass strict validation, and no high/critical npm vulnerabilities remain after dependency refresh.

Not yet "commercialization complete" until two business/legal decisions are closed:

1. Decide the public license. `LICENSE.txt` currently allows commercial use, but it is a custom license with extra obligations. It should not be marketed as OSI-standard open source without legal review. Recommended standard option: AGPL-3.0-or-later if CSM is to stay copyleft and cover hosted/service use.
2. Accept or remove the remaining dev-only npm audit findings. They are moderate `uuid` advisories under Microsoft Office Add-in debug tooling and are not part of the packaged runtime, but they will still appear in due-diligence scans of `addin/package-lock.json`.

## Changes made during this audit

- Fixed the v1.3 build gate mismatch: `addin/scripts/validate-static.js` now expects `cloud_features: true`, matching `VERSION.json` and release tests.
- Hardened manual placeholder merge restore:
  - `server/tc_engine.py` now records occurrence-level restore originals for merged placeholders.
  - `server/api.py` stores `placeholder_restore_overrides` in new maps created by `/v4/current/remask-session`.
  - Merge controls are resolved from old preview placeholders to the current remasked map, so valid merges are not silently dropped if numbering changes.
  - Invalid/unresolvable merge pairs now fail clearly instead of pretending success.
- Added regression coverage proving `prepare -> preview -> merge -> remask -> restore` preserves original surface forms such as `Jan Kowalski` and `Anna Nowak`.
- Exposed the existing mapping action "Zmień typ" in the mapping preview UI and renamed merge action to "Scal z..." for clearer reviewer workflow.
- Updated add-in dev dependencies:
  - `office-addin-debugging` to `^6.1.1`
  - `office-addin-dev-certs` to `^2.0.9`
  - `protobufjs` override to `^8.6.5`
- Fixed `tests/run_pytest.py` so project cache folders are cleaned after the isolated test subprocess.

## Validation run

- `python tests/run_pytest.py`: 597 passed, 3 skipped. Skips require `CSM_REVISION_SIDECAR_CMD` pointing to a compiled real sidecar binary.
- `dotnet test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj --no-restore`: 11 passed.
- `node addin/scripts/validate-static.js --build`: passed.
- `python tools/evaluate_pseudonymization_grid.py`: 16/16 cases passed, 0 false negatives, 0 false positives, 0 restore failures.
- `python tools/verify_gazetteer_licenses.py --strict`: passed for 5 bundled gazetteer sources.
- `npm audit --package-lock-only --audit-level=high`:
  - root package: 0 vulnerabilities.
  - `addin`: no high/critical findings; 9 moderate dev-tooling findings remain.

## Licensing assessment

### Own CSM license

`LICENSE.txt` permits commercial use, copying, distribution and modification. However, it is not a standard OSI license and includes additional obligations such as sending modifications back to the licensor. This is likely acceptable for a controlled beta/community license, but risky if the product is described as standard "open source".

Recommended path before public commercialization:

- choose `AGPL-3.0-or-later` if strong copyleft and service/SaaS coverage are desired;
- or `GPL-3.0-or-later` if only distributed desktop binaries matter;
- or dual-license AGPL + commercial license if paid proprietary embedding is planned.

Changing the license should update `LICENSE.txt`, `LICENSE-BETA.txt`, `LICENSE.pdf`, `addin/taskpane.html`, package metadata, installer wording and release notes together.

### External code and packages

- Python wheelhouse: MIT/BSD/Apache/PSF family licenses only in bundled wheels inspected locally.
- .NET sidecar: `Clippit` is MIT according to NuGet/GitHub. It is commercially compatible; current CSM pins 3.4.3 on net8. Newer 3.5.x targets net10, so do not upgrade blindly.
- npm packages: direct add-in dev packages are MIT. They are development tooling, not runtime files installed by CSM.
- Office.js is loaded from Microsoft CDN in `addin/taskpane.html`; keep this documented as an external Microsoft runtime dependency.
- Gazetteers: bundled external public-data sources are CC0; internal stoplists are marked proprietary/internal and pass the local license gate.
- Bielik model options configured in the installer point to SpeakLeash GGUF models. Public model cards declare Apache 2.0. Keep model license references in release documentation because the model is optional and may be downloaded outside the CSM package.

Primary references checked:

- Clippit GitHub / MIT: https://github.com/sergey-tihon/Clippit
- Clippit NuGet / MIT: https://www.nuget.org/packages/Clippit
- Bielik 11B v3 GGUF / Apache 2.0: https://huggingface.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF
- Bielik Minitron 7B v3 GGUF: https://huggingface.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF
- Bielik 1.5B v3 GGUF: https://huggingface.co/speakleash/Bielik-1.5B-v3.0-Instruct-GGUF

## Pseudonymization assessment

Strengths:

- Span-safe replacement is used instead of blind global replacement.
- DOCX package processing covers body, comments, headers, footers, metadata/custom XML, tracked changes and images.
- Polish legal-domain false positive guards exist for headings, role labels and ambiguous surname/common-word cases.
- Identity ledger and alias categories reduce inconsistent placeholder families.
- Manual `always`, `never`, category override and merge controls are now covered by tests.

Remaining precision/recall improvement path:

- Build a larger legal-text benchmark beyond the current 16-case grid: pleadings, contracts, notarial deeds, correspondence, invoices, signatures, scanned/OCR-heavy documents.
- Add metrics by category: recall, precision, false positive class, restore exactness, and time/memory by document size.
- Add specific cases for initials, abbreviated names, foreign names, multi-party firms, CEIDG trade names, KGL-like partnership names, inflected aliases and repeated same-surname parties.
- Keep Bielik as review-only unless model outputs are constrained and regression-tested; do not let LLM findings directly mutate the replacement plan without deterministic validation.
- Treat images/OCR as a separate product feature. Current image redaction is safer than pretending image text is analyzed.

## Security and privacy assessment

Good state:

- Sensitive API routes require `X-CSM-Token`.
- CORS is restricted to localhost origins plus explicit environment configuration.
- Static add-in server refuses wildcard binds.
- Maps are DPAPI-protected on Windows and have retention cleanup.
- Audit log is metadata-only with allow-listed fields.
- Error sanitization redacts paths, filenames and obvious identifiers.

Commercialization gaps:

- Add a published privacy notice explaining local processing, local maps, retention windows, Office.js CDN, optional Bielik/Ollama/VPS mode and support-log handling.
- Add a vulnerability disclosure policy and a documented security update process.
- Sign installer binaries and publish checksums.
- Produce SBOM/third-party notices for Python wheels, NuGet package, npm dev tooling and optional model dependencies.
- Review VPS provisioning scripts separately before offering cloud deployment commercially, because those paths handle provider API keys and org tokens.

## Release recommendation

Technically acceptable for a controlled pilot after the changes above.

For public commercial/open-source release, block on:

1. Standard license decision and synchronized license artifacts.
2. SBOM + third-party notices.
3. Installer/code signing and checksum publication.
4. Written privacy/security policy.
5. Manual Windows/Word smoke on a clean machine with the actual installer artifact.
6. Decision on remaining moderate npm dev-tooling advisories: accept as dev-only, isolate from source release, or replace Office Add-in debug tooling.
