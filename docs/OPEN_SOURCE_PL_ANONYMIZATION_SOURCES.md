# CSM — Open-Source Polish Anonymization Sources

**Version:** CSM v1.0  
**Last updated:** 2026-05-20

This document lists every external data source evaluated or used for Polish named-entity recognition and pseudonymization in CSM. It must be kept up to date. Machine-readable metadata is in `server/gazetteers/licenses.json`.

---

## Sources accepted and bundled

### PESEL registry — first names (`dane.gov.pl` dataset 1667)

| Attribute | Value |
|-----------|-------|
| URL | https://dane.gov.pl/pl/dataset/1667 |
| License | CC0 1.0 |
| Downloaded | 2026-01-20 |
| Entries bundled | 7,949 first names (occurrences ≥ 30) |
| File | `server/pl_gazetteers.py::FIRST_NAMES` |
| Runtime use | Yes (offline) |

Polish government open-data portal. Contains first names of living persons registered in the PESEL system with occurrence counts. CC0 — no restrictions on bundling or redistribution.

**Masking rule:** A first name alone never triggers masking. It is used as evidence that a preceding or following Title Case token is part of a PERSON entity.

---

### PESEL registry — surnames (`dane.gov.pl` dataset 1681)

| Attribute | Value |
|-----------|-------|
| URL | https://dane.gov.pl/pl/dataset/1681 |
| License | CC0 1.0 |
| Downloaded | 2026-01-20 |
| Entries bundled | 8,636 surnames (occurrences ≥ 500) |
| File | `server/pl_gazetteers.py::SURNAMES` |
| Runtime use | Yes (offline) |

Surnames of living persons from PESEL registry. CC0 — no restrictions. Threshold ≥ 500 occurrences is used to exclude very rare surnames that could inadvertently identify an individual.

**Masking rule:** Surname alone never triggers masking. Requires: (a) valid first name in FIRST_NAMES at same span, or (b) explicit legal context (Pan/Pani/Mec./adw./PESEL/zamieszkały).

---

### TERYT/SIMC — locality names (`dane.gov.pl` dataset 188)

| Attribute | Value |
|-----------|-------|
| URL | https://dane.gov.pl/pl/dataset/188 |
| Alternate source | https://eteryt.stat.gov.pl/ |
| License | CC0 1.0 |
| Downloaded | 2026-01-20 |
| Entries bundled | 69,984 (nominative + genitive forms) |
| File | `server/pl_gazetteers.py::LOCALITIES` |
| Runtime use | Yes (offline) |

Official Polish register of locality names ("Wykaz urzędowych nazw miejscowości i ich części", MSWiA). Includes every city, and deduplicated village/osada/kolonia names. Both nominative and genitive forms are included.

**Masking rule:** Locality alone never triggers masking. Requires address context: `zamieszkały w`, `z siedzibą w`, `siedzibą w`, `adres`, `ul.`, postal code, or a party-data row.

---

## Sources evaluated and rejected

### BAN-PL (Benchmark for Anonymization — Polish)

| Attribute | Value |
|-----------|-------|
| Paper | https://arxiv.org/abs/2308.10592 |
| License | **Not verified** |
| Bundled | No |
| Reason | Dataset license not confirmed. Social-media corpus — not legal text. May be used for test case inspiration after license clarification with authors. |

---

### PIIBench

| Attribute | Value |
|-----------|-------|
| Paper | https://arxiv.org/abs/2604.15776 |
| Repo | https://github.com/pritesh-2711/pii-bench |
| License | **Not verified** |
| Bundled | No |
| Reason | Not a Polish-primary corpus. Label mapping used as architecture inspiration only. |

---

### PolEval 2018 NER / Polish Proper Names

| Attribute | Value |
|-----------|-------|
| Paper | https://arxiv.org/abs/1811.10418 |
| License | **Not verified** |
| Bundled | No |
| Reason | NER strategy used as architecture inspiration. Dataset license must be confirmed before data import. |

---

### PlWordNet / Słowosieć

| Attribute | Value |
|-----------|-------|
| URL | http://plwordnet.pwr.wroc.pl/ |
| License | **Requires individual verification** |
| Bundled | No |
| Reason | The negative-evidence word list in `pl_common_words_negative.sample.json` is hand-authored, not derived from PlWordNet. PlWordNet may be integrated after license review. |

---

### ParaNames

| Attribute | Value |
|-----------|-------|
| Paper | https://arxiv.org/abs/2202.14035 |
| Repo | https://github.com/bltlab/paranames |
| License | **Not verified** |
| Bundled | No |
| Reason | Size and license not verified. Future candidate for ORG/LOC gazetteers. |

---

### Korpusomat

| Attribute | Value |
|-----------|-------|
| URL | https://korpusomat.pl/ |
| License | **Not verified** |
| Bundled | No |
| Reason | Useful for comparative NER annotation and test corpus creation. Cannot embed models or data without explicit license. |

---

### Wikidata (Polish entities)

| Attribute | Value |
|-----------|-------|
| URL | https://query.wikidata.org/ |
| License | CC0 |
| Bundled | No (yet) |
| Reason | CC0 — eligible for future bundling. Candidate for court names (`COURT` category), public institutions, and organization aliases. Must be built via `tools/build_pl_gazetteers.py --source wikidata` into a small filtered gazetteer — full dumps must not be committed. |

---

## Policy enforcement

- `tools/verify_gazetteer_licenses.py` — enforces that every `bundled: true` source in `licenses.json` has a valid, non-restricted license.
- Build fails if any bundled source has `license` = `unknown`, `research-only`, `non-commercial`, or `no-redistribution`, or has missing `license_url` / `downloaded_at`.
- See `docs/PL_PSEUDONYMIZATION_RESOURCE_POLICY.md` for the full scoring and masking policy.
