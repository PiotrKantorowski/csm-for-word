# CSM 1.4 RC34 — edge hardening report

Date: 2026-07-04
Base: CSM 1.4 RC33 public business corpus hardening
Scope: pseudonymization accuracy hardening only. Court judgments and blank forms were intentionally excluded from the new benchmark scope.

## Executive summary

RC34 adds a conservative edge-case hardening layer for public business/legal documents. It targets classes that can still appear in real B2B/legal workflows but were weaker after RC33: public-aid beneficiary lines, procurement identifiers, reverse addresses without street prefixes, property unit identifiers, business registry/platform IDs, full/short business-name labels and notarial act numbers.

The restore architecture and map format were not changed.

## What changed

### 1. Public-aid / SUDOP-like beneficiary rows

Added stronger detection for rows such as:

- `Beneficjent pomocy: Jan Kowalski Software`
- `EORI PL123456789000000`

A pure two-token natural person remains a person, but a person name plus trade-name tail is treated as a contractor/JDG line.

### 2. Procurement and public-notice identifiers

Added label-anchored detection for:

- `Postępowanie nr ZP.271.1.2026`
- `Ogłoszenie BZP nr 2026/BZP 00123456/01`
- `TED 2026/S 123-456789`

This also prevents the trailing TED/BZP number segment from being misclassified as a phone number.

### 3. Reverse-order addresses without street prefix

Added context-anchored full-address masking for rows such as:

- `Adres korespondencyjny: 39-200 Dębica, Pustynia 84F`
- `Adres: 00-001 Warszawa, Prosta 1 lok. 2`

Before RC34, only the postcode could be masked in these variants.

### 4. Property unit identifiers

Added detection for property-unit references:

- `lokal nr 12`
- `miejsce postojowe MP-45`
- `garaż nr G-2`

These receive a new placeholder family: `[NR_LOKALU_n]`.

### 5. Business IDs beyond NIP/KRS/REGON

Added `BUSINESS_ID` detection for:

- `EORI`
- `LEI`
- `D-U-N-S` / `DUNS`
- `GLN`
- `vendor_id`
- `tenant_id`
- `supplier_id`
- `merchant_id`

These receive a new placeholder family: `[ID_BIZNESOWY_n]`.

### 6. Business-name labels with false-positive guard

Added stricter handling for:

- `Nazwa skrócona: KXG Legal`
- `Nazwa pełna: Kancelaria Prawna Kantorowski Głąb i Wspólnicy sp.j.`

At the same time, RC34 deliberately does not mask generic document/product titles such as:

- `Nazwa pełna: Regulamin sklepu internetowego.`

### 7. Notarial act numbers

Added label-anchored masking for:

- `Numer aktu notarialnego NZ/1234/2026`

Existing repertory detection remains unchanged.

## Restore / reversibility verification

The following functions are byte-for-byte identical at source-function hash level versus RC33:

- `save_map`
- `load_map`
- `mask_ooxml`
- `restore_ooxml`
- `restore_ooxml_parts`
- `restore_ooxml_package_bytes`
- `_restore_text_value`

Detailed hashes are saved in:

- `CSM_RC34_RESTORE_FUNCTION_HASH_CHECK.json`

## Test results

Targeted RC34 edge tests:

```text
8 passed
```

RC30-RC34 benchmark/regression tests:

```text
165 passed
```

Pseudonymization/legal regression segment:

```text
151 passed
```

Full test suite run in deterministic file chunks:

```text
764 passed
3 skipped
0 failed
```

Skipped tests require a compiled .NET sidecar and `CSM_REVISION_SIDECAR_CMD`, which is not available in this Linux container.

Static validation:

```text
CSM lint validation passed for v1.4.
CSM build validation passed for v1.4.
```

## Remaining honest limitations

RC34 still should not be described as guaranteeing perfect anonymization. The remaining hard cases are mainly:

- OCR-damaged text;
- tables where labels and values are badly merged;
- one-word names that are also common nouns or places, without legal context;
- unusual foreign identifiers without an explicit label;
- documents that intentionally avoid standard labels.

The safe operating model remains: automatic pseudonymization + final human review before sending any legal document to an external AI system.
