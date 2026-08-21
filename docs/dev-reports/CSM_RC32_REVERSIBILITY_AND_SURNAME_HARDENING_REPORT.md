# CSM 1.4 RC32 — reversibility and surname hardening report

Date: 2026-07-04
Base package: CSM 1.4 RC31 final pseudonymization package
Scope: verify reversibility compatibility with CSM 1.4, confirm Głąb/Jedliński pseudonymization, and improve safe surname-only detection.

## 1. Reversibility compatibility with CSM 1.4

The reversibility flow was not redesigned or replaced. RC32 keeps the same map/restore mechanism as CSM 1.4:

- `save_map`
- `load_map`
- `mask_ooxml`
- `restore_ooxml_with_report`
- `restore_ooxml`
- `restore_xml_part_with_report`
- `restore_ooxml_parts`
- `mask_ooxml_package_bytes`
- `restore_ooxml_package_bytes`

I compared the function bodies against the original CSM 1.4 package. The SHA-256 hashes of those function bodies are identical in original 1.4 and RC32:

| Function | SHA-256 |
|---|---|
| `save_map` | `2629c1870f38a426fbe9ae105e236ade500a3aeba7ef64cb8b3819170eea2678` |
| `load_map` | `5969640af1b6f5297887dded9c05b8398e77c058f9d72d9dff67fdab51b364b5` |
| `mask_ooxml` | `1781a47327dc2e4ae50917ebc924232f66fa85d79b20ff04d79f87da26d77b30` |
| `restore_ooxml_with_report` | `31b3d1e7a4300c0e92a6d6affd77f6141a6a9eeb2e6db14de6465cf3eb9401cd` |
| `restore_ooxml` | `456c62050d9d42320c5d97e5fad2df42633697e445a4403e037b83f91ef6d1c3` |
| `restore_xml_part_with_report` | `aa6db4a80a37b8191fbbfa55ab1db4028f9f531d9cbec31d0764a8f07705d30f` |
| `restore_ooxml_parts` | `8d272368cf2edbb166a67fc5488775b444bfd1a0aad392f513173ccb1a85e59f` |
| `mask_ooxml_package_bytes` | `8a323610b180b2040716bf6d6af2297130fa3094d18d8312c19be6d371597067` |
| `restore_ooxml_package_bytes` | `ef99768b4aaffc30f288248d715e70a3c4b11ee13eff11fd3515998adc02eb72` |

Conclusion: RC32 changes only detection coverage and tests/reports. It does not change the restore architecture or placeholder map format.

## 2. Głąb and Jedliński verification

RC31 already masked these names in full-name/title/company contexts, for example:

- `Radca prawny Anna Głąb` -> masked
- `adw. Marek Jedliński` -> masked
- `r.pr. Jana Jedlińskiego` -> masked
- `Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp.j.` -> masked as company

RC31 did not mask surname-only procedural mentions without prior context, such as:

- `Głąb wniósł apelację.`
- `Jedliński złożył oświadczenie.`
- `Powód Jedliński złożył pozew.`
- `Pozwany Głąb wniósł odpowiedź.`

RC32 adds coverage for those patterns.

## 3. Additional pseudonymization hardening in RC32

Added conservative surname-only legal-context recognizers:

- party/role + surname, e.g. `Powód Jedliński`, `Pozwany Głąb`, `świadek Nowak`, `pełnomocnik Kowalski`;
- sentence-start surname + legal action verb, e.g. `Jedliński złożył`, `Głąb wniósł`, `Kowalski podpisał`, `Nowak wskazał`.

The new recognition is guarded by:

- single-token surname shape validation;
- legal/procedural context requirement;
- PESEL surname gazetteer check where available;
- fallback for common Polish surname suffixes such as `-ski`, `-ska`, `-wicz`, `-czyk`, `-niak`;
- legal/role/common-word stoplists.

False-positive guard examples verified:

- `Warszawa wskazała nowe zasady.` -> not masked;
- `Umowa została podpisana.` -> not masked;
- `Sąd wskazał, że pozew oddalono.` -> not masked;
- `Strona złożyła dokumenty w terminie.` -> not masked.

## 4. New tests

Added: `tests/test_rc32_reversibility_and_surnames.py`

It checks:

- text restore roundtrip for the new surname-only patterns;
- OOXML restore roundtrip for the new surname-only patterns;
- masking of `Głąb` and `Jedliński` in legal contexts;
- no regressions on common false-positive examples.

## 5. Validation results

Segmented pytest run completed:

```text
722 passed
3 skipped
0 failed
```

The 3 skipped tests require compiled real `.NET revision sidecar` and `CSM_REVISION_SIDECAR_CMD`. This is consistent with the previous RC31 limitation.

Static/build validation:

```text
CSM build validation passed for v1.4.
```

## 6. Honest limitation

RC32 improves surname-only detection, but it still intentionally avoids global masking of every capitalized single word. This is correct for legal documents because words such as `Strona`, `Sąd`, `Warszawa`, `Umowa` or locality names can otherwise become false positives.

For strongest safety in production, use RC32 with the existing post-mask residual review and manual review before sending anonymized content to any external AI tool.
