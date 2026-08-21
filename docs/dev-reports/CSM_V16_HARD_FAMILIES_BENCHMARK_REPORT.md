# CSM v1.6 — hard-families benchmark extension report

Date: 2026-07-13
Base: CSM v1.6 manual-rules rebuild
Scope: extend automated quality measurement to the families RC34 explicitly named as unmeasured limitations. No detection code was changed as part of this report — this is a measurement exercise, not a fix.

## Why this exists

Every prior quality claim for CSM (grid 23/23, adversarial benchmark 24/24) is measured on synthetic documents authored to exercise known detector rules. RC34 and RC35 both stated the real residual weak spots by name — OCR-damaged text, flattened tables, bare ambiguous surnames, unlabeled foreign identifiers, documents that avoid standard labels — but no benchmark ever tested them. A 100% pass rate on a benchmark that never contains your known weaknesses is not evidence those weaknesses are fixed.

This report adds `server/data/regression_cases/pseudonymization_hard_families_v16.json` (10 cases) targeting exactly those named families, and runs it through the existing evaluator (`tools/evaluate_pseudonymization_grid.py --cases ...`).

## Method note (one false alarm caught and discarded)

An initial probe of the "documents that avoid standard PESEL/NIP labels" family appeared to find a serious bug: a bare 11-digit number was not masked unless the literal word "PESEL" appeared nearby. Before writing this up, the same probe was re-run with a number confirmed to actually pass the Polish PESEL checksum (`44051401359`, verified via `validators.valid_pesel`). Under multiple generic, label-free wordings ("numer", "identyfikator", "numer zamówienia to..."), the checksum-valid number was masked correctly in every case. The original alarm was caused by using a checksum-invalid test number that happened to appear in an existing fixture — that fixture only exercises the label-present branch, not checksum validity. This is now locked in as a positive regression-guard case (`F1`) instead of a false bug report.

## Results

```
Cases: 10
PASS: 6
FAIL_FALSE_NEGATIVE: 4
FAIL_WRONG_CATEGORY: 4 (paired with the same 4 false negatives)
FAIL_FALSE_POSITIVE: 0
RESTORE_FAIL: 0
```

Full pytest suite after adding the new file: 787 passed, 3 skipped (unchanged — this is a data-only addition).

### Confirmed real gaps (4)

| Case | Family | Finding |
|---|---|---|
| `A1_ocr_pesel_spaces` | OCR damage | A checksum-valid PESEL split by OCR into space-separated digit groups (`4 4 0 5 1 4 0 1 3 5 9`) is not detected at all — the bare-digit regex requires 11 contiguous digits. |
| `B1_merged_words_name` | Merged/glued extraction | A first name + surname glued to the following word with no space (`JanKowalskiprzekazał`) is not detected as PERSON — token-boundary detection requires separate capitalised words. |
| `D1_bare_ambiguous_surname` | Bare ambiguous surname | An inflected bare surname that is also a common noun (`Kowalem`, from *kowal* = blacksmith), with no first name anchoring it anywhere in the document, is not masked — even with legal-adjacent context ("w sprawie ugody"). This is the identity-ledger ambiguity guard behaving as designed (it only masks a bare surname when it uniquely identifies one already-detected person), but it means a document that only ever refers to someone by surname leaks that surname completely. |
| `E2_address_no_anchor_label` | Address without anchor label | The exact reverse-order address pattern RC34 fixed (`39-200 Dębica, Pustynia 84F`) is only masked when preceded by an anchor label such as "Adres korespondencyjny:". The same address text elsewhere in a sentence ("Wysyłkę należy skierować na...") only gets the postcode masked — city and street+number leak in full. RC34's fix is label-anchored, not a context-free full-address pattern. |

### Confirmed regression guards (6, now locked into the benchmark)

| Case | Family | What it protects |
|---|---|---|
| `A2_ocr_missing_diacritics` | OCR damage | A name missing Polish diacritics is still detected as PERSON. |
| `B2_label_glued_pesel` | Merged/glued extraction | A label glued directly to a PESEL value with zero separator, and an invalid checksum, is still masked via the existing label-context safety rule. |
| `C1_table_pipe_separated_row` | Flattened table | A pipe-separated single-line table row (header line + data row) correctly masks PERSON, PESEL and ADDRESS in the same row. Tables are not automatically broken. |
| `E1_address_with_anchor_label` | Address without anchor label | The RC34 reverse-order address fix still works when the anchor label is present. |
| `F1_checksum_valid_pesel_generic_wording` | Checksum robustness | A checksum-valid PESEL is masked under any generic wording, including wording that explicitly triggers the order-id exclusion for NIP-shaped numbers. |
| `F2_nip_order_context_disambiguation` | Checksum robustness | A NIP-shaped number following "Zlecenie numer" is correctly classified as `PROJECT_ID`, not `NIP` — the exhibit/order-number disambiguation still holds. |

## What this changes about prior quality claims

The core detector was not touched. The 100%-on-benchmark claims for the grid and adversarial-benchmark corpora remain accurate for what they measure — synthetic documents built around known rule families. This report does not contradict them; it adds a second, harder measurement surface that was previously entirely absent, and that surface currently sits at 60% (6/10), concentrated in exactly the families the engineering reports already named as unresolved. This number should not be read as "CSM is 60% accurate" — it is a small, targeted probe, not a representative sample of real documents — but it is the first actual measurement of these specific named weaknesses, replacing what was previously an assumption.

## Suggested next steps (not done here)

1. `A1` (OCR-spaced PESEL) and `E2` (unanchored reverse address) look the cheapest to close: both are pattern-matching gaps, not ambiguity/safety trade-offs.
2. `D1` (bare ambiguous surname) is a genuine precision/recall trade-off, not a simple fix — loosening the ambiguity guard would raise recall but risks masking common nouns as people elsewhere in the corpus. Any change here needs the full grid + adversarial benchmark re-run alongside this file to catch new false positives.
3. `B1` (glued words) is the least common in practice (most DOCX/PDF text extraction preserves word spacing; this is mainly a raw-OCR risk) and the highest-effort fix (requires a different tokenization strategy), so it is reasonable to leave as a documented, accepted limitation for now.
4. This file should be re-run on every future engine change alongside the existing grid and adversarial benchmark, the same way `test_manual_rules_v16_semantics.py` guards the manual-rules subsystem.
