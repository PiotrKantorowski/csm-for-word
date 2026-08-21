# CSM Polish pseudonymization rulebook — rc14 addendum

This addendum supplements `CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md`.

## 1. Span-safe masking is mandatory

For Polish legal documents, a detected sensitive value must be replaced at the accepted detection spans, not blindly everywhere in the document.

Reason: some personal surnames and localities are also ordinary Polish words or business words, for example:

- Mucha,
- Pustynia,
- Lis,
- Kruk,
- Wrona,
- Nowina,
- Góra,
- Zielony / Zielona in firm names.

If the engine detects `Pani Mucha`, it may mask that occurrence, but it must not automatically replace every later bare occurrence of `Mucha` unless that later occurrence is independently detected as a person/company/address alias.

## 2. Title + single-token person references

Mask title-anchored single-token references:

```text
Pani Mucha
Pan Mucha
Pana Muchy
Panu Musze
Panią Muchę
```

The current minimum implementation covers the direct title + capitalized token form and should be expanded with inflection tests where reliable.

Do not mask unrelated bare ordinary words unless independently supported by context.

## 3. Party labels must remain readable

Procedural labels such as these are document structure and should remain visible:

```text
Powód
Pozwany
Wierzyciel
Dłużnik
Wnioskodawca
Uczestnik
```

The entity after the label should be masked, not the label itself.

Correct:

```text
Pozwany [COMPANY_1]
Powód [PERSON_1]
```

Incorrect:

```text
[COMPANY_1]
```

when the placeholder swallowed `Pozwany Mucha sp. z o.o.`.

## 4. Company names after `przeciwko`

In pleadings, the phrase `przeciwko` often introduces the opposing party. A company written in all caps after `przeciwko` should be treated as a confidential party name even without a legal suffix.

Example:

```text
Powód Jan Nowak wnosi pozew przeciwko OLIMP LABORATORIES.
```

Expected:

```text
Powód [PERSON_1] wnosi pozew przeciwko [COMPANY_1].
```

## 5. Locality after `siedzibą w`

The locality after `siedzibą w` can be sensitive and may be masked in address/company context.

However, the detector must not capture following lowercase prose.

Correct:

```text
z siedzibą w [ADDRESS_1] wnosi odpowiedź
```

Incorrect:

```text
[ADDRESS_1] = "Pustyni wnosi odpowiedź"
```

## 6. Regression tests required

At minimum, the following tests must remain green:

```text
tests/test_rc13_polish_pseudonymization_rules.py
tests/test_rc14_polish_edge_cases.py
tests/test_pseudonymization_extended_recommendations.py
tests/test_legal_lexicon_contracts_pleadings.py
```

Each new legal pseudonymization rule should include:

1. masking test,
2. non-masking false-positive test,
3. restore test: plain -> pseudonymized -> restored must equal original.
