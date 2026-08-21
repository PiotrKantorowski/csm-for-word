# server/gazetteers/

Polish language gazetteers for CSM pseudonymization.

## Runtime gazetteers

| File | Type | Entries | Source |
|------|------|---------|--------|
| `../pl_gazetteers.py` (FIRST_NAMES) | First names | 7,949 | PESEL registry, dane.gov.pl #1667, CC0 |
| `../pl_gazetteers.py` (SURNAMES) | Surnames | 8,636 | PESEL registry, dane.gov.pl #1681, CC0 |
| `../pl_gazetteers.py` (LOCALITIES) | Localities | 69,984 | TERYT/SIMC/MSWiA, dane.gov.pl #188, CC0 |

Runtime gazetteers are embedded in `server/pl_gazetteers.py` as Python frozensets for zero-overhead offline lookup.

## Auxiliary files (this directory)

| File | Purpose |
|------|---------|
| `licenses.json` | Machine-readable source/license metadata for all bundled data |
| `pl_legal_labels_negative.json` | Hard-negative list: document section headings that must never be masked |
| `pl_common_words_negative.sample.json` | Surnames that are also common Polish nouns — negative evidence |
| `pl_first_names.sample.json` | 40-entry sample from FIRST_NAMES, for tests and documentation |
| `pl_surnames.sample.json` | 40-entry sample from SURNAMES, for tests and documentation |
| `pl_places.sample.json` | 20-entry sample from LOCALITIES with genitive forms |
| `pl_streets.sample.json` | Placeholder — street gazetteer not yet integrated at runtime |

## Design principles

1. **No blind gazetteer masking.** Gazetteer presence alone is not a mask trigger. It provides scoring *evidence*. Masking requires legal/personal context.
2. **Scoring components**: `context_score + pattern_score + gazetteer_score + morphology_score − negative_score`. See `docs/PL_PSEUDONYMIZATION_RESOURCE_POLICY.md`.
3. **Offline operation.** CSM runs offline. Gazetteers are pre-built and version-controlled. No network calls during document processing.
4. **License compliance.** Every bundled source must have a valid entry in `licenses.json`. The build tool (`tools/verify_gazetteer_licenses.py`) enforces this.

## Adding new gazetteers

1. Choose a CC0 or other compatible source.
2. Run `tools/build_pl_gazetteers.py --source <source-id>` to download and process.
3. Add a `licenses.json` entry.
4. Embed the data in `pl_gazetteers.py` or add a new `.json` file here.
5. Write tests in `tests/test_pl_gazetteer_context_scoring.py` and `tests/test_pl_gazetteer_false_positive_guards.py`.
6. Run `tools/verify_gazetteer_licenses.py` — must exit 0.
