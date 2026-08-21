# CSM Engine Architecture v0.2.5

## Design direction

The engine remains local and Word-focused. It does not replace the Word add-in with any external tool. It borrows architectural ideas from:

- Presidio: modular recognizer/detector architecture and conflict resolution;
- pii-anon: identity ledger, stable token families, regression tests;
- scrubadub: simple detector wrappers and placeholder replacement patterns.

It does not integrate pii-redaction or piicatcher at this stage.

## Main layers

1. **Detectors** - regex and context-based detectors for Polish legal documents.
2. **Optional NLP** - spaCy Polish NER can be enabled locally with `CSMW_ENABLE_SPACY=1`.
3. **Optional local Bielik** - a local Ollama/OpenAI-compatible Bielik endpoint can be enabled with `CSMW_ENABLE_BIELIK=1`; CSM only accepts exact text spans returned as JSON.
3. **IdentityLedger** - clusters aliases, inflections, domains and related mentions into stable placeholder families.
4. **Transforms** - creates placeholders and reversible replacement maps.
5. **OOXML layer** - masks Word OOXML text nodes and, when provided by the add-in, multiple document parts such as body, headers and footers.
6. **Restore validation** - checks expected, missing and unknown placeholders before and after restore.
7. **Map protection** - on Windows wraps local maps with current-user DPAPI encryption.

## Current limitations

- Headers and footers are processed only if Word exposes them through Office.js in the user's environment.
- Comments, footnotes, text boxes, metadata, embedded files, images and scanned stamps require further work.
- NLP and Bielik are optional and disabled by default to avoid heavy dependencies and slow local inference.
- The tool is operational pseudonymization, not irreversible anonymization.


## Dodatkowo w v0.2.5
- dodano tryb pełnego pakietu DOCX, który próbuje objąć komentarze, przypisy, endnotes, nagłówki, stopki, metadane i customXml;
- dodano endpointy /mask_docx_package, /restore_docx_package i /original_docx_package;
- tryb pakietu ma fallback do dotychczasowego trybu OOXML części dokumentu.


## v0.2.20 Security & Control

Wersja v0.2.20 dodaje lokalny token API `X-CSM-Token`, automatyczne czyszczenie map według TTL, metadany audit log bez wartości jawnych oraz rozszerzone stoplisty prawno-biznesowe. Podejście jest inspirowane: Presidio (kontrola wycieków i brak logowania PII), pii-anon (identity/token ledger i metadane audytowe) oraz scrubadub (detektory + stoplisty/filtry), bez integrowania ciężkich silników wprost.


## v0.2.21 Address hardening

Wersja v0.2.21 rozszerza reguły adresowe o warianty adresu ulicznego bez kodu pocztowego, w tym formy z przyimkiem `w/we`, miejscowością w odmianie i zapisem alternatywnym typu `Krośnie/Krosno`. Reguła nadal nie maskuje samodzielnej nazwy miejscowości poza bezpośrednim kontekstem adresu.



## v0.2.30 Simple UX and OOXML tracked-change path

Wersja v0.2.30 upraszcza podstawowy panel do dwóch akcji: pseudonimizacji dla Claude i przywrócenia wersji jawnej. Diagnostyka oraz przywracanie z kopii awaryjnej zostały przeniesione do sekcji zaawansowanej.

Dla dokumentów ze śledzeniem zmian panel nie używa już pełnego zastępowania dokumentu przez `insertFileFromBase64` jako ścieżki roboczej, ponieważ w realnym Wordzie może to zwracać `GeneralException` albo prowadzić do niepożądanej normalizacji historii redakcyjnej. Standardowa ścieżka dla takich dokumentów to teraz OOXML parts: aplikacja pobiera części OOXML dostępne przez Office.js, maskuje tekst oraz wrażliwe atrybuty XML, a następnie wstawia zmodyfikowane części z zachowaniem istniejących `w:ins`, `w:del`, `w:delText` i pokrewnych znaczników.

Jeżeli dokument zawiera rewizje i nie da się bezpiecznie zastosować ścieżki OOXML, aplikacja przerywa operację i nie przechodzi do trybu tekstowego.

## v0.2.29 Clean package hotfix

Wersja v0.2.29 nie zmienia logiki pseudonimizacji względem v0.2.28. Hotfix usuwa z paczki instalacyjnej wygenerowane katalogi `backups` powstałe podczas testów i zostawia wyłącznie pliki startowe `backups/.keep` oraz `backups/WARNING.txt`.

## v0.2.28 UX integration guard for prepare failures

Wersja v0.2.28 naprawia ścieżkę panelu Word po refaktorze UX. Jeżeli przygotowanie dokumentu kończy się błędem, blok `finally` nie może już wywołać `refreshDocumentState(false)`, bo neutralny stan panelu ukrywałby komunikat błędu i sprawiał wrażenie, że kliknięcie wykonało pracę bez zmiany dokumentu. Refresh jest wykonywany tylko po potwierdzonym sukcesie operacji.

Dodatkowo zwykłe dokumenty nie są blokowane wyłącznie dlatego, że host Worda nie ujawnia jednoznacznie `changeTrackingMode`. Twarde wymaganie kontroli śledzenia zmian pozostaje dla dokumentów zawierających realne znaczniki rewizji w pakiecie DOCX.

## v0.2.27 Overlapping person detection in tracked deletions

Wersja v0.2.27 dodaje nakładający się detektor osób oparty na lookahead. Standardowe dopasowanie regex jest nie-nakładające się, więc w tekście typu `Usunięto Adam Nowicki` mogło najpierw sprawdzić i odrzucić parę `Usunięto Adam`, a następnie nie dojść do właściwego nazwiska `Adam Nowicki`. Ma to znaczenie szczególnie w `w:delText`, bo tekst usunięty w śledzeniu zmian nadal jest częścią pakietu DOCX i musi zostać zspseudonimizowany bez spłaszczania rewizji.


## v0.2.26 DOCX package restore report hardening

Wersja v0.2.26 doprecyzowuje raport przywracania w trybie pełnego pakietu DOCX. Restore agreguje teraz `missing_total`, `missing_placeholders`, `unknown_total`, `unknown_placeholders` i `found_total` dla całego pakietu, a nie tylko dla poszczególnych części XML. Dodatkowo placeholdery w atrybutach XML, np. autorach komentarzy i rewizji, są przywracane tak jak tekst węzłów, dzięki czemu panel nie zgłasza fałszywych braków po prawidłowym restore.

## v0.2.25 Revision-preserving UX and DOCX mode

Wersja v0.2.25 zmienia zasadę pracy ze śledzeniem zmian: standardowa pseudonimizacja nie akceptuje, nie odrzuca ani nie spłaszcza rewizji. Jeżeli w pełnym pakiecie DOCX wykryto znaczniki rewizji Word (`w:ins`, `w:del`, `w:moveFrom`, `w:moveTo` i pokrewne), panel wybiera tryb pełnego pakietu DOCX, maskuje dane również w treści rewizji i zachowuje znaczniki historii redakcyjnej. Gdy bezpieczna operacja nie jest możliwa, dokument nie jest oznaczany jako gotowy dla Claude, a tryb tekstowy nie jest używany jako fallback dla dokumentów z rewizjami. Panel uproszczono do jednej głównej akcji zależnej od stanu dokumentu oraz dodano łatwą ponowną pseudonimizację po przywróceniu danych.

## v0.2.23 Word panel safety hardening

Wersja v0.2.23 dodaje po stronie panelu Word zabezpieczenia procesowe: ostrzeżenie przy ryzyku związanym ze śledzeniem zmian, szczegółowy raport brakujących placeholderów przy przywracaniu danych oraz stan ostrzegawczy po depseudonimizacji, gdy dokument zawiera jawne dane. W v0.2.25 scenariusz zgody na spłaszczenie został zastąpiony zasadą zachowania rewizji albo przerwania operacji.


## v0.2.22 API text-size limit

Wersja v0.2.22 dodaje limit 2 MB dla pola `text` w endpointach `/mask` i `/scan`. Żądania przekraczające limit są odrzucane statusem HTTP 413 przed uruchomieniem silnika pseudonimizacji, aby ograniczyć ryzyko zablokowania lokalnego serwera przez nadmiernie duży payload.
