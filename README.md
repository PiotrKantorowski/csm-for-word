# CSM for Word v1.6

CSM (Claude Safe Mode) to dodatek do Microsoft Word z lokalnym backendem, który pseudonimizuje polskie dokumenty prawne **przed** wysłaniem ich do modelu językowego, a po pracy z modelem przywraca dane jawne w tym samym dokumencie. Dokument nie opuszcza komputera: wykrywanie i podmiana danych dzieją się w procesie działającym na `127.0.0.1`, a mapa odwracająca podmianę jest szyfrowana kluczem użytkownika Windows (DPAPI).

Projekt powstał w Kancelarii Prawnej Kantorowski, Głąb i Wspólnicy sp.j. na własne potrzeby i jest udostępniony publicznie na [Licencji Otwartej CSM](LICENSE.txt) — wolno go używać komercyjnie, badać i modyfikować, ale modyfikacje muszą pozostać na tej samej licencji.

## Problem, który to rozwiązuje

Radca prawny, który chce dać model językowy do przeczytania pozwu albo umowy, staje przed wyborem: albo wysyła do chmury dane objęte tajemnicą zawodową, albo ręcznie zaciera nazwiska, PESEL-e i sygnatury, a potem ręcznie wpisuje je z powrotem do gotowego pisma. CSM zamienia to na dwa kliknięcia w panelu Worda:

```txt
Utwórz i otwórz kopię do pracy z Claude   ->  dokument_CSM_anon.docx (z placeholderami)
Utwórz i otwórz wersję jawną              ->  dokument z powrotem z danymi jawnymi
```

Placeholdery są czytelne po polsku i trzymają tożsamość: ta sama osoba jest zawsze `[OSOBA_3]`, jej odmienione nazwisko to `[OSOBA_3_ALIAS_1]`, a nie nowy byt. Dzięki temu model rozumie, kto z kim zawarł umowę, nie wiedząc, kto to jest.

## Zakres wykrywania

Silnik jest pisany pod polski dokument prawny, nie pod ogólny tekst. Rozpoznaje między innymi osoby wraz z odmianą przez przypadki i aliasami, spółki i kontrahentów (także bez sufiksu prawnego, po kontekście roli procesowej), adresy w formie ulicznej, wiejskiej i „z siedzibą w", PESEL, NIP, REGON, KRS, IBAN/NRB, dowody osobiste, paszporty, sądy, sygnatury akt, repertoria notarialne, księgi wieczyste, decyzje administracyjne, e-maile, telefony, domeny i adresy URL.

Reguły są dobierane kontekstowo, bo w polskim tekście prawnym granica jest cienka: `Mucha sp. z o.o.` to firma, `Pani Mucha` to osoba, a `mucha` to owad. Pełna siatka kategorii, z przykładami pozytywnymi i negatywnymi, leży w [`docs/PSEUDONYMIZATION_MAPPING_GRID.md`](docs/PSEUDONYMIZATION_MAPPING_GRID.md).

Dokumenty ze śledzeniem zmian są obsługiwane bez spłaszczania historii redakcyjnej. CSM operuje na częściach OOXML i maskuje także tekst usunięty (`w:delText`), który fizycznie zostaje w pliku DOCX. Jeżeli nie da się tego zrobić bezpiecznie, operacja jest przerywana, a nie degradowana do trybu tekstowego.

## Czego to nie robi

To pseudonimizacja operacyjna, odwracalna, a nie anonimizacja. Mapa istnieje i jest w stanie odtworzyć dane jawne.

Skuteczność wykrywania zależy od treści dokumentu i konfiguracji. Żadna konfiguracja nie gwarantuje wykrycia wszystkich danych osobowych ani wszystkich informacji objętych tajemnicą zawodową. Dokument po pseudonimizacji trzeba przejrzeć przed przekazaniem go do modelu — panel pokazuje pozycje wątpliwe właśnie do tego. Odpowiedzialność za zgodność z RODO i tajemnicą zawodową zostaje po stronie użytkownika (§ 5 licencji).

Skany i obrazy nie są czytane: w tej wersji `ocr_features` jest wyłączone.

## Instalacja

Wymagany jest Windows i Microsoft Word obsługujący dodatki Office.js (Office 365 albo Word 2016 i nowszy).

1. Rozpakuj paczkę albo sklonuj repozytorium do dowolnego folderu tymczasowego.
2. Uruchom `ZAINSTALUJ_CSM.cmd`.
3. Na pytanie UAC odpowiedz **Tak**.

Instalator kopiuje CSM do `C:\CSM`, rejestruje dodatek w Wordzie, instaluje certyfikat HTTPS dla `localhost`, czyści cache dodatku, tworzy jedną ikonę **CSM** na pulpicie i włącza autostart lokalnych usług po zalogowaniu. Gotowy instalator dla osób, które nie chcą budować projektu, jest dołączony do najnowszego wydania.

Skryptów z katalogu `tools` nie uruchamia się ręcznie — korzysta z nich instalator i panel serwisowy.

## Codzienna praca

Po instalacji CSM startuje razem z systemem, więc w typowym dniu nie trzeba nic klikać. Ikona **CSM** na pulpicie otwiera panel serwisowy:

```txt
START      - awaryjnie uruchom CSM w tle
STOP       - zatrzymaj CSM
CLEAN      - wyczysc cache Worda
NAPRAW     - odswiez instalacje
ODINSTALUJ - usun CSM
```

Panel można zamknąć, a CSM nadal będzie dostępny dla dodatku w Wordzie. Silnik zatrzymuje się dopiero po wybraniu STOP.

### Zasada, o której trzeba wiedzieć

Żeby zmiany wprowadzone po pseudonimizacji trafiły do wersji jawnej, „Utwórz i otwórz wersję jawną" trzeba kliknąć z panelu otwartego w pliku `*_CSM_anon.docx`. Jeśli Word trzyma panel przy oryginale, CSM sam próbuje pobrać otwarty `*_CSM_anon.docx` przez Word COM albo sięga po plik zapisany w sesji. Gdy zapisany plik jest nadal bazową, niezmienioną kopią, CSM zatrzymuje przywracanie i prosi o przełączenie się do `*_CSM_anon.docx`, zapisanie go albo ręczne wskazanie zmienionego pliku. Lepiej dostać komunikat niż cicho stracić pracę wykonaną z modelem.

### Jak czytać raport anonimizacji

Po utworzeniu `_CSM_anon.docx` panel pokazuje podsumowanie:

```txt
unikalne wartosci   - ile roznych wartosci zostalo zastapionych placeholderami
pozycje do kontroli - ile ostrzezen lub potencjalnych pozostalosci wymaga recznego sprawdzenia
kategorie danych    - typy wykrytych danych, np. PERSON, COMPANY, PESEL, ADDRESS
ryzyka pozostale    - klasy danych, ktore moga wymagac sprawdzenia w dokumencie
zakres DOCX         - ktore czesci pliku analizowano: tresc, naglowki, stopki, komentarze, metadane
```

Raport nie zawiera surowych podejrzanych wartości, żeby sam nie stał się źródłem wycieku. Kopie lądują w folderze sesji jako `report_prepare.json` i `report_restore.json`.

### Ręczne reguły

Panel pozwala poprawić wynik po pseudonimizacji: dodać frazy do listy „zawsze anonimizuj", wskazać frazy „nigdy nie anonimizuj", zmienić kategorię albo scalić placeholdery (`[OSOBA_8] => [OSOBA_3]`, po jednej parze w linii). Scalanie służy do tego, żeby ta sama osoba rozpoznana jako dwa byty — odmiana nazwiska, inicjał, alias — wróciła do jednej tożsamości.

Zasady dopasowania:

- Frazy działają w granicach słów, bez rozróżniania wielkości liter. Reguła `Ala` nie ruszy słowa „otrzymała".
- Reguła „zawsze" z kategorią `OSOBA`, `FIRMA` lub `SAD` obejmuje odmianę przez przypadki i trafia do tej samej rodziny placeholderów co wykrycia automatyczne.
- Reguła „nigdy" wyłącza wykrycie tylko wtedy, gdy obejmuje je w całości. Danych zweryfikowanych sumą kontrolną (PESEL, NIP, REGON, IBAN, dowód, paszport) nie odsłoni — chyba że reguła zostanie poprzedzona znakiem `!`, co jest świadomym wymuszeniem (`!44051401359`).
- „Podgląd skutków reguł" pokazuje przed zastosowaniem, ile wystąpień doda każda reguła, które wykrycia wyłączy i które reguły nie mają w tym dokumencie żadnego efektu. Żaden plik nie jest przy tym zmieniany.

Reguły można zapisać na stałe dla klienta lub sprawy albo dla całej kancelarii. Zapis jest lokalny i szyfrowany tak samo jak mapy.

## Architektura

```txt
addin/            panel Office.js w Wordzie (pliki statyczne po HTTPS na :3000)
server/           lokalne API FastAPI na 127.0.0.1:8787 - detektory, identity ledger, warstwa OOXML
sidecar/          CSM.RevisionSidecar (.NET 8) - operacje na rewizjach DOCX poza zasiegiem Office.js
tools/            skrypty PowerShell: start, stop, naprawa, certyfikat, diagnostyka
installer/        Inno Setup (CSM-Setup.iss) i skrypt budujacy
tests/            pakiet pytest, benchmarki jakosci, testy kontraktow
docs/             dokumentacja silnika, siatka kategorii, standardy QA
docs/dev-reports/ raporty z audytow i iteracji rozwojowych
```

Warstwy silnika: detektory regexowe i kontekstowe, opcjonalny NER, `IdentityLedger` sklejający aliasy i odmiany w stabilne rodziny placeholderów, transformacje i mapa odwracalna, warstwa OOXML, na końcu walidacja przywracania porównująca placeholdery oczekiwane, brakujące i nieznane. Szczegóły w [`docs/ENGINE-ARCHITECTURE.md`](docs/ENGINE-ARCHITECTURE.md).

Bezpieczeństwo lokalne: każde żądanie do API wymaga nagłówka `X-CSM-Token` z tokenem generowanym od nowa przy każdym STARCIE, mapy i migawki są kasowane po TTL z `config.json` (domyślnie 30 dni), a log audytowy zapisuje metadane bez wartości jawnych.

### Detektory opcjonalne

Domyślnie wyłączone, żeby nie ciągnąć ciężkich zależności ani nie zwalniać pracy:

| Zmienna | Co włącza |
|---|---|
| `CSMW_ENABLE_SPACY=1` | polski NER ze spaCy |
| `CSMW_ENABLE_BIELIK=1` | lokalny Bielik przez Ollama lub endpoint zgodny z OpenAI ([`docs/BIELIK-LOCAL-DETECTOR.md`](docs/BIELIK-LOCAL-DETECTOR.md)) |
| `CSMW_ENABLE_GLINER=1` | detektor GLiNER |

Z Bielika CSM przyjmuje wyłącznie dokładne fragmenty tekstu zwrócone jako JSON, nigdy swobodnej odpowiedzi modelu.

## Rozwój

```bash
python -m pip install -r server/requirements.txt
npm ci
npm run lint
python tests/run_pytest.py -q
```

Stan na wydanie v1.6: **790 testów przechodzi, 3 pominięte**. Pominięte to testy integracyjne sidecara, które wymagają skompilowanego `CSM.RevisionSidecar.exe` wskazanego zmienną `CSM_REVISION_SIDECAR_CMD`.

Testy pilnują nie tylko poprawności, ale i jakości pseudonimizacji. `tests/test_hard_families_benchmark_v16.py` przypina dokładny zbiór przypadków, których silnik świadomie jeszcze nie obsługuje: jeśli któryś zacznie przechodzić, test też pada, żeby wymusić aktualizację raportu i świadomą decyzję. Korpus benchmarkowy w `tests/fixtures/` jest zbudowany z publicznych wzorów dokumentów, nie z akt klientów.

Budowa instalatora wymaga Inno Setup:

```bash
powershell -NoProfile -ExecutionPolicy Bypass -File installer/build-csm-setup.ps1
```

CI (`.github/workflows/build-csm-installer.yml`) na `windows-latest` buduje i testuje sidecar .NET, uruchamia lint statyczny, cały pakiet pytest, a na końcu składa instalator.

## Czego nie ma w repozytorium

- `addin/csm-token.js` — token lokalnego API, generowany przy każdym STARCIE. Wzorzec pliku to `addin/csm-token.js.example`.
- `backups/` — awaryjne kopie przywracania z komputera użytkownika. Mogą zawierać dane objęte tajemnicą zawodową, dlatego zostaje tylko `backups/WARNING.txt`.
- `installer/output/` — zbudowany instalator. Trafia do wydań, nie do gita.

## Licencja i oznaczenia

[Licencja Otwarta CSM 1.0](LICENSE.txt), copyleft na prawie polskim. Wolno używać w dowolnym celu, w tym komercyjnym, kopiować, badać, dekompilować i modyfikować. Modyfikacje muszą być udostępniane na tej samej licencji, z pełnym kodem źródłowym, oznaczeniem autora i daty zmiany, oraz przesłane licencjodawcy w ciągu 30 dni od pierwszej dystrybucji (§ 3–4).

Licencja nie obejmuje prawa do używania nazw i logotypów kancelarii ani znaku „CSM" poza oznaczeniem autorstwa i informacją, że modyfikacja bazuje na tym oprogramowaniu (§ 6). Pliki w `assets/` są objęte tym zastrzeżeniem.

Kontakt: kontakt@kancelariakantorowski.pl. Zgłoszenia problemów: Issues w tym repozytorium.
