# CSM — Polish Pseudonymization Resource Policy

**Version:** CSM v1.0  
**Last updated:** 2026-05-20

---

## 1. Overriding principles

1. **No blind gazetteer masking.** The presence of a token in a gazetteer (names, localities) is NOT sufficient to trigger masking. Gazetteer lookup provides scoring *evidence*, not a masking decision.
2. **Context is required.** Masking requires legal or personal context: a title prefix (Pan/Pani/Mec./adw.), a role keyword (Powód/Pozwany/Pełnomocnik), an identity marker (PESEL/zamieszkały/siedziba), or explicit address context.
3. **Span-safe replacement.** Every match must have exact start/end offsets. Restore (`restore_ooxml`) must recover the exact original string. No lossy masking.
4. **No NC-licensed data.** Only sources with licenses explicitly allowing redistribution (CC0, public domain, or verified permissive) may be bundled in CSM.
5. **Offline runtime.** Network access is forbidden during document processing. All gazetteers must be pre-built and version-controlled.

---

## 2. Scoring framework

Each entity candidate receives a composite score before a masking decision is made:

```
score = context_score
      + pattern_score
      + gazetteer_score
      + morphology_score
      − negative_score
```

### 2.1 Component definitions

| Component | What it measures |
|-----------|-----------------|
| `context_score` | Strength of legal or personal context near the span (title prefix, role word, PESEL, address label, etc.) |
| `pattern_score` | Confidence from the structural pattern detector (e.g., two Title Case tokens, company suffix regex, court name regex) |
| `gazetteer_score` | Positive evidence from FIRST_NAMES, SURNAMES, LOCALITIES gazetteers |
| `morphology_score` | Polish case inflection match (e.g., genitive form correctly matched against gazetteer nominative) |
| `negative_score` | Penalty when the token appears in `pl_common_words_negative` without context, or matches `pl_legal_labels_negative` |

### 2.2 Minimum thresholds

| Entity type | Condition | Min score |
|-------------|-----------|-----------|
| PERSON | First name + surname (two tokens) | 0.55 |
| PERSON | Title prefix (Pan/Pani/Mec.) + surname | 0.60 |
| PERSON | Surname alone | **Forbidden** unless PESEL or birth data present |
| COMPANY | Company legal-form suffix (sp. z o.o., S.A., etc.) | 0.55 |
| COMPANY | Role word (Klient/Wykonawca) + entity name | 0.60 |
| COMPANY | ALL CAPS token without suffix | **Forbidden** if looks like document heading |
| PLACE/ADDRESS | Postal code + locality | 0.55 |
| PLACE/ADDRESS | Street prefix + name + building number | 0.55 |
| PLACE/ADDRESS | Locality alone | **Forbidden** unless after `zamieszkały w`, `siedziba w`, `adres`, etc. |

### 2.3 Example score traces

**`Pani Mucha podpisała dokument.`**
```
context_score  = +0.50  (title prefix "Pani")
pattern_score  = +0.15  (single Title Case token)
gazetteer_score= +0.20  (SURNAMES contains "Mucha")
negative_score = −0.05  (also in pl_common_words_negative — offset by title prefix)
──────────────────────
total          =  0.80  → MASK as PERSON ✓
```

**`Na stole siedziała mucha.`**
```
context_score  =  0.00  (no personal/legal context)
pattern_score  =  0.00  (lowercase token — does not match POLISH_CAP)
gazetteer_score=  0.00  (lowercase 'mucha' not in SURNAMES set)
negative_score =  0.00
──────────────────────
total          =  0.00  → DO NOT MASK ✓
```

**`zamieszkały w Pustyni`**
```
context_score  = +0.50  (ADDRESS_ZAMIESZKALY pattern fires)
pattern_score  = +0.20  (Title Case token after address keyword)
gazetteer_score= +0.25  (LOCALITIES contains "Pustyni")
negative_score =  0.00
──────────────────────
total          =  0.95  → MASK as ADDRESS ✓
```

**`Na pustyni było gorąco.`**
```
context_score  =  0.00  (no address context)
pattern_score  =  0.00  (lowercase token)
total          =  0.00  → DO NOT MASK ✓
```

---

## 3. Hard negative lists

### 3.1 Legal document labels (`pl_legal_labels_negative.json`)

Two-token section headings and form-field labels that are never PII:

- `Dane Klienta`, `Nazwa Spółki`, `Adres Siedziby`, `Numer Umowy`, `Data Umowy`
- `Postanowienia Końcowe`, `Warunki Płatności`, `Przedmiot Umowy`, `Strony Umowy`
- ~90 total entries

Applied in two pipeline stages:
1. `_GAZETTEER_LABEL_STOPLIST` — before gazetteer lookup
2. `_GLOBAL_LABEL_STOPLIST` — after all detectors in `collect_findings`

### 3.2 Common-word surnames (`pl_common_words_negative.sample.json`)

Surnames that are also common Polish nouns: mucha (fly), lis (fox), wilk (wolf), kot (cat), baran (ram), etc.

Without explicit legal context, these words generate `negative_score = −0.40`, which prevents masking at all thresholds. With a title prefix (Pan/Pani) or PESEL, the negative score is overridden.

---

## 4. Required test cases

The following scenarios must pass in every release. See `tests/test_pl_gazetteer_false_positive_guards.py` and `tests/test_pl_gazetteer_context_scoring.py`.

| Input | Expected | Test file |
|-------|----------|-----------|
| `Na stole siedziała mucha.` | no PERSON | false_positive_guards |
| `Pani Mucha podpisała dokument.` | PERSON('Mucha') | context_scoring |
| `Jan Mucha podpisał dokument.` | PERSON('Jan Mucha') | context_scoring |
| `Dane Klienta` | no PERSON/COMPANY | false_positive_guards |
| `Nazwa Spółki` | no PERSON/COMPANY | false_positive_guards |
| `Adres Siedziby` | no PERSON/COMPANY | false_positive_guards |
| `Klienta = "NUTRIFARM" sp. z o.o. reprezentuje Jan Kowalski.` | COMPANY + PERSON, balanced quotes | context_scoring |
| `Powód: OLIMP LABORATORIES sp. z o.o.` | COMPANY (not Powód) | context_scoring |
| `Pozwany Mucha sp. z o.o.` | COMPANY('Mucha sp. z o.o.') | context_scoring |
| `zamieszkały w Pustyni` | ADDRESS('Pustyni') | context_scoring |
| `Na pustyni było gorąco.` | no PLACE/ADDRESS | false_positive_guards |
| `ul. Dąbrowskiego 23/35, 42-200 Częstochowa` | ADDRESS_FULL | context_scoring |
| `Sąd Rejonowy w Rzeszowie` | COURT | context_scoring |
| `Sąd stwierdził, że...` | no COURT | false_positive_guards |

Every test also verifies: `pseudonymize(input) → restore → input` (exact roundtrip).

---

## 5. Prohibited actions

1. Adding full Wikidata/OSM/TERYT dumps to the repository.
2. Bundling data with `license = non-commercial` or `license = research-only`.
3. Using a dataset with `license = unknown`.
4. Using the gazetteer as a global replace (blind masking).
5. Masking surname tokens without legal context.
6. Removing existing regression tests.
7. Marking a release as final if Word/install/restore tests have not been run.
