# Public benchmark source files

This directory contains public legal-form source files used for benchmark traceability in the CSM pseudonymization accuracy work.

The executable benchmark does **not** use client documents and does **not** contain professional-secrecy material. The benchmark cases in `tests/fixtures/public_legal_pseudonymization_benchmark.json` use synthetic PII inserted into structures inspired by these public forms.

`manifest.json` records the source URL, byte size and SHA-256 digest for every bundled file.

To refresh or verify the files, run:

```bash
python tools/fetch_public_legal_benchmark_sources.py --verify-only
python tools/fetch_public_legal_benchmark_sources.py
```

The script preserves cached files if internet access is unavailable.
