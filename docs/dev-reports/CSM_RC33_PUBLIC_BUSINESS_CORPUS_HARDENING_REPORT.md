# CSM RC33 — public business/legal corpus pseudonymization hardening

Date: 2026-07-04
Base package: CSM 1.4 RC32 reversibility + surname hardening
Scope: improve pseudonymization using public internet-available materials while excluding court judgments and blank forms.

## User constraint

The RC33 benchmark and hardening intentionally exclude:

- court judgments, because they are already anonymized and do not represent raw client documents well;
- blank forms, because they mostly test labels rather than real document flow.

Used instead:

- public contract-register structures;
- public administrative-decision structures from UODO/UOKiK contexts;
- public procurement/civil-contract templates;
- SUDOP-style public-aid beneficiary/search-result structures;
- B2B contract identifiers and contact bundles inspired by public business documents.

## Engine changes

Changed file: `server/redactor.py`.

### 1. Contract-register / public-business party rows

Added `CONTRACT_REGISTRY_PARTY_PATTERN` and helper classification for rows such as:

- `Kontrahent/nazwa: Pani Klaudia Borczyk`
- `Kontrahent/nazwa: Kolporter spółka z ograniczoną odpowiedzialnością`
- `Kontrahent/nazwa: G.L.M. Spółka z ograniczona odpowiedzialnością`
- `Kontrahent/nazwa: "JARD" SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ`
- `Kontrahent/nazwa: Bauza.pl MACIEJ BAUZA`
- `Kontrahent/nazwa: Mariusz Jaworski prowadzący działalność gospodarczą pod firmą „Autopromo”, Warszawa`

The recognizer masks the party value while preserving labels and surrounding contract metadata.

### 2. Administrative-decision numbers

Hardened `DECYZJA_ADM` so CSM masks only the actual decision reference, not the label words.

Before-risk example:

- `Decyzja Prezesa UODO nr DKN.5112.33.2022`

RC33 result:

- keeps `Decyzja Prezesa UODO nr`
- masks `DKN.5112.33.2022`

Also removed the collision where `PERMIT_ID` could treat `Prezesa` as a permit/licence identifier.

### 3. Contract / project identifiers

Expanded `PROJECT_ORDER_CONTEXT_PATTERN` for public procurement-style references, for example:

- `Umowa nr BRPO-WZP.261.123.2026`
- `Umowa nr GDDKIA-OSZ.2411.4.2025`
- `Umowa nr GDDKiA-O.Sz.D-3.2411.4.2025`
- `Numer referencyjny środka pomocowego SA.12345`

Preserved existing behavior for contract numbers that encode company tokens, e.g. `NOVUS/OMNITEX/B2B/05/2026/FIK`: company tokens remain masked, neutral B2B/date/FIK segments remain visible.

### 4. Alias false-positive hardening

Adjusted company alias generation to avoid broad last-token aliases from two-word company names. This prevents false positives such as masking `Dynamics` in product names like `Dynamics 365` after detecting `One Dynamics Sp. z o.o.` as a contractor.

### 5. Login descriptor hardening

Expanded login-context detection for phrases such as:

- `login panelu autopromo_admin`

so the actual login is masked rather than only the descriptor word `panelu`.

## New tests and fixtures

Added:

- `tests/fixtures/public_business_legal_corpus_benchmark_rc33.json`
- `tests/test_rc33_public_business_corpus_hardening.py`
- `tests/fixtures/public_sources_raw/manifest_rc33.json`
- `tests/fixtures/public_sources_raw/README_RC33.md`

New RC33 benchmark:

- 32 public-business/legal corpus cases;
- source categories: contract register, administrative decisions, public procurement contracts, public aid/SUDOP-style rows, B2B contact bundles, false positives;
- every case requires reversible roundtrip.

## Verification

Commands run:

```text
PYTHONPATH=server pytest -q tests/test_rc33_public_business_corpus_hardening.py
```

Result:

```text
34 passed
```

Broader target regression suite:

```text
PYTHONPATH=server pytest -q tests/test_rc30_public_legal_pseudonymization_benchmark.py tests/test_rc31_public_source_manifest.py tests/test_rc32_reversibility_and_surnames.py tests/test_rc33_public_business_corpus_hardening.py tests/test_pseudonymization_quality_gate_hardening.py tests/test_pseudonymization_extended_recommendations.py tests/test_legal_identifier_numbers.py tests/test_identity_document_person_company_context.py tests/test_contextual_persons_and_roles.py tests/test_legal_lexicon_contracts_pleadings.py
```

Result:

```text
182 passed
```

Full test set was executed in file-group segments because a single monolithic pytest run exceeded the container wall-clock limit after passing most of the suite. Segment totals:

```text
756 passed
3 skipped
0 failed
```

Skipped tests:

- 3 real `.NET sidecar` integration tests requiring `CSM_REVISION_SIDECAR_CMD` and a compiled sidecar.

Build validation:

```text
npm run build --silent
```

Result:

```text
CSM build validation passed for v1.4.
```

Static add-in validation:

```text
node addin/scripts/validate-static.js
```

Result:

```text
CSM lint validation passed for v1.4.
```

## Reversibility

RC33 does not change restore architecture, map persistence, OOXML restore, or placeholder restoration semantics. The added benchmark cases use `make_replacements(...) -> _restore_text_value(...)` roundtrip assertions.

Existing RC32 reversibility tests remain green.

## Limitations

- RC33 does not claim perfect pseudonymization. It improves coverage for additional business/legal structures.
- Real Word + Windows + compiled .NET sidecar tests still need to be executed outside this Linux container.
- The benchmark excludes client documents and professional-confidential material.
- The RC33 fixture records public source URLs and patterns. Binary downloads for new RC33 sources were not bundled because remote DNS was unavailable in the build container. Existing RC31 raw source files remain intact.

## Restore-function hash check vs RC32

The following core restore/map functions are byte-identical at function-source level between RC32 and RC33:

- `save_map`
- `load_map`
- `mask_ooxml`
- `restore_ooxml`
- `restore_ooxml_parts`
- `restore_ooxml_package_bytes`
- `_restore_text_value`

Detailed hashes are stored in:

```text
CSM_RC33_RESTORE_FUNCTION_HASH_CHECK.json
```
