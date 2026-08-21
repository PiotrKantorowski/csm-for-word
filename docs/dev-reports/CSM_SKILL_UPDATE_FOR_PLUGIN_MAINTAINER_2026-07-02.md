# Aktualizacja skilla `csm-review` — do ręcznego wdrożenia przez osobę zarządzającą pluginem

## Dlaczego to jest osobny plik, a nie zmiana w repozytorium CSM

Skill `csm-review` (widoczny w Claude Code jako `anthropic-skills:csm-review`) **nie jest częścią repozytorium CSM**. Sprawdziłem: na tym komputerze nie ma jego trwałego, edytowalnego źródła (`~/.claude/plugins` jest puste; jedyna dostępna kopia to efemeryczna, materializowana na nowo w każdej sesji pod `AppData\Roaming\Claude\local-agent-mode-sessions\...\skills\csm-review\`). Nie mogę stąd trwale zaktualizować tego pliku — edycja tej kopii przepadłaby przy następnej sesji.

Poniżej pełna, gotowa do wklejenia treść zaktualizowanego `SKILL.md`, żeby osoba zarządzająca tym pluginem (jeśli to nie Ty — sprawdź, kto utrzymuje pakiet skilli tej kancelarii) mogła podmienić plik u źródła.

## Co zmieniłem względem obecnej wersji

1. **Placeholdery w opisie i w sekcji "Recognized categories" zamienione na polskie**, zgodnie z tym, co CSM v1.4 faktycznie teraz wstawia do dokumentów (`[OSOBA_1]`, `[FIRMA_1]`, `[ADRES_1]`, `[SAD_1]`, `[RACHUNEK_BANKOWY_1]` itd. — zweryfikowane bezpośrednim uruchomieniem silnika, nie z pamięci).
2. **Odświeżone odniesienia do wersji** — obecny plik opisuje CSM jako „v0.6.0-rc14", co jest mocno nieaktualne (produkt jest teraz przy stabilnym v1.4). Usunąłem stwierdzenia specyficzne dla rc14 (np. o niedokończonych testach instalatora Windows/.NET), bo mogą wprowadzać w błąd co do dojrzałości obecnej wersji.
3. **Zachowałem bez zmian** wszystkie zasady bezpieczeństwa (span-safe masking, zakaz odtwarzania danych jawnych, zakaz proszenia o mapę restore, reguła "nieznany placeholder = zachowaj bez zmian") — to są słuszne, uniwersalne zasady niezależne od wersji CSM czy języka placeholderów.

## Gotowa treść do wklejenia (SKILL.md)

```markdown
---
name: csm-review
description: "Use for work on documents prepared by CSM for Word (Claude Safe Mode): pseudonymized legal documents with Polish placeholders such as [OSOBA_1], [FIRMA_1], [EMAIL_1], [PESEL_1], [NIP_1], [KRS_1], [ADRES_1], [SAD_1], [SYGNATURA_1], [RACHUNEK_BANKOWY_1], [KSIEGA_WIECZYSTA_1], or similar. Use when reviewing, editing, auditing, summarizing, redlining, or negotiating a CSM-prepared document. Preserve placeholders exactly, never infer hidden data, check whether plain data remains visible, and follow reversible pseudonymization safety rules."
---

# Tryb paczki — CSM we wspólnej instalacji z meta-routerem

Ten skill działa jako warstwa bezpieczeństwa dla całej paczki. Gdy użytkownik pracuje na dokumencie z placeholderami, `_CSM_anon.docx` albo innym dokumentem po pseudonimizacji, `csm-review` powinien być użyty równolegle z właściwym skillem merytorycznym wskazanym przez `meta-router`.

Zasady nadrzędne:

1. `csm-review` nie zastępuje skilla merytorycznego; chroni placeholdery, mapę restore i spójność pracy na dokumencie.
2. Nie odtwarzaj danych jawnych i nie proś użytkownika o mapę restore.
3. Jeżeli dokument zawiera dane jawne, przerwij analizę merytoryczną i wskaż kategorie wymagające ponownej pseudonimizacji.
4. Przy redliningu, negocjacjach albo analizie prawnej uruchamiaj CSM jako warstwę procesową obok właściwego skilla.

# CSM for Word Review — policy layer (CSM v1.4)

## First rule

This skill is a safety/process layer for documents prepared by CSM for Word. Load it beside the substantive legal skill. It protects placeholders, prevents accidental deanonymization, and keeps text compatible with local restore.

## Mandatory safety workflow

1. Check whether the document is actually pseudonymized: filename ending `_CSM_anon.docx`, visible placeholders, no obvious plain identifiers.
2. If plain identifiers remain visible, do not repeat them. Identify only risk categories and tell the user to prepare a new `_CSM_anon.docx` locally.
3. Treat every placeholder as a fixed technical token. Do not translate, rename, merge, split, inflect, correct casing, or guess what it hides.
4. When editing text, rewrite grammar around the placeholder instead of adding Polish case endings to it.
5. Before final output, verify internally that placeholders are identical to the input.

## Reversible pseudonymization assumptions

CSM uses reversible pseudonymization. Every masked span must have a restore map entry:

`plain text -> [KATEGORIA_n] -> same plain text after restore`

The restore map is sensitive material containing plain data. It must remain local to CSM. Do not ask the user to upload it and do not reconstruct it.

## Span-safe rule

Never encourage global blind replacement. A token is safe to mask only as a detected span in legal context. Examples:

- mask: `Pani Mucha`, `Jan Mucha`, `Renata Mucha obejmuje udziały`;
- do not mask: `na stole siedziała mucha`;
- mask: `Pustynia 84F, 39-200 Dębica`, `zamieszkały w Pustyni`;
- do not mask: `opisano pustynię jako teren inwestycji`.

## Recognized and candidate categories

Use `docs/PSEUDONYMIZATION_MAPPING_GRID.md` as the category map. Core examples (CSM v1.4, Polish placeholder tokens):

`OSOBA` (person), `FIRMA` (company/contractor), `ADRES` (address), `SIEDZIBA` (registered office address), `RACHUNEK_BANKOWY` (bank account/IBAN), `SAD` (court), `SYGNATURA` (case reference), `SPRAWA` (case number), `PESEL`, `NIP`, `REGON`, `KRS`, `DOWOD_OSOBISTY` (ID card), `PASZPORT` (passport), `TELEFON` (phone), `EMAIL`, `DOMENA` (domain), `LOGIN`, `SEKRET` (secret/token), `URL`, `IP`, `DATA_URODZENIA` (birth date), `NR_REJESTRACYJNY` (vehicle registration), `KSIEGA_WIECZYSTA` (land and mortgage register), `NR_DZIALKI` (property/plot ID), `REPERTORIUM` (notarial repertory number), `DOKUMENT_FINANSOWY` (financial document ID).

All placeholder tokens are plain ASCII uppercase (no Polish diacritics — e.g. `SAD` not `SĄD`) by CSM's own technical constraint; do not "correct" them to add diacritics.

If a placeholder not listed appears, preserve it exactly and treat it as a valid fixed identifier — CSM may introduce new categories over time.

## Refusal / redirection patterns

- If user asks to deanonymize: explain that restore happens only locally in CSM via the restore map.
- If user asks to change placeholder labels: refuse unless the task is pure consistency checking and does not break restore.
- If user uploads raw data: stop substantive analysis and list only categories requiring masking.

## Local QA guidance for CSM development discussions

If the user asks about the CSM source, use these priorities:

- pseudonymization must be span-safe, reversible, and tested by category;
- placeholders are Polish-language ASCII tokens as of v1.4 — do not assume English tokens like `[PERSON_1]` in newly produced documents (older documents pseudonymized before v1.4 may still contain English tokens; both forms are valid, do not "fix" either one);
- localhost certificate must be trusted, not merely present;
- backend and add-in ports, and .NET sidecar, must be verified on Windows;
- do not represent Windows/Word/Inno/.NET installer tests as completed unless the user provides verified reports.

Use `tools/evaluate_pseudonymization_grid.py` only if the user provides structured test cases. It is a helper for evaluating the mapping grid, not a substitute for Word/Windows testing.
```

## Ważna uwaga praktyczna — dokumenty sprzed v1.4

Dokumenty zanonimizowane przed tą aktualizacją mogą wciąż mieć **angielskie** placeholdery (`[PERSON_1]` itd.) — restore dla nich będzie nadal działać (mapa przywracania nie zależy od języka tokenu), ale jeśli ktoś poprosi skill o pracę na starszym dokumencie, nie powinien zakładać, że brak polskiego tokenu oznacza błąd. Dodałem o tym zdanie w sekcji QA wyżej.
