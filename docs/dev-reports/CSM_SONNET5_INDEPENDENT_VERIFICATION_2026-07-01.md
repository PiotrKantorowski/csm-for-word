# CSM — niezależna weryfikacja (Sonnet 5) i wytyczne wdrożeniowe dla Opus 4.8

Data: 2026-07-01. Zakres: niezależna, od zera przeprowadzona weryfikacja stanu CSM v1.3 pod kątem komercjalizacji, wykonana bez zakładania, że ustalenia raportu `CSM_COMMERCIALIZATION_AUDIT_2026-07-01.md` są prawdziwe. Wszystkie automatyczne bramki uruchomiono ponownie od zera; wszystkie ustalenia poniżej poparte są konkretnym dowodem (plik/linia, treść zamaskowanego tekstu, diff), nie samą deklaracją.

**Rola tego dokumentu**: to nie jest lista zadań do wykonania przeze mnie — to materiał wejściowy dla Opusa 4.8, który wprowadzi zmiany. Każde ustalenie ma wskazane miejsce w kodzie i sugerowany kierunek naprawy, żeby Opus nie musiał odkrywać tego od nowa.

---

## 0. Wynik uruchomienia bramek automatycznych (reprodukcja niezależna)

Wszystko odtworzone i zgodne z deklaracją raportu z 2026-07-01 — potwierdzam, nie tylko wierzę na słowo:

| Bramka | Wynik |
|---|---|
| `python tests/run_pytest.py` | 597 passed, 3 skipped (skip wymaga skompilowanego sidecara — oczekiwane) |
| `dotnet test sidecar/CSM.RevisionSidecar.Tests` | 11 passed |
| `node addin/scripts/validate-static.js --build` | passed |
| `python tools/evaluate_pseudonymization_grid.py` | 16/16 PASS, 0 błędów |
| `python tools/verify_gazetteer_licenses.py --strict` | OK, 5 źródeł |
| `npm audit` (root) | 0 podatności |
| `npm audit` (addin) | 0 high/critical, 9 moderate w narzędziach deweloperskich (uuid via office-addin-debugging) |

Wniosek: techniczna baza jest solidna i nieskłamana w poprzednim raporcie. Punkt 1 zlecenia użytkownika ("poprawność działania rozwiązania") — potwierdzony na poziomie zautomatyzowanym. Pozostaje wyłącznie ręczny smoke test w realnym Wordzie na czystej maszynie z instalatorem — tego nie da się zweryfikować z tej sesji (brak środowiska Windows+Word+Office.js w tym kontekście wykonania).

---

## 1. Licencja (zgodnie z decyzją: zostajemy przy własnej licencji, bez zmiany na AGPL/GPL)

### Potwierdzone: `LICENSE.txt` ≡ `LICENSE-BETA.txt`
Bajt w bajt identyczne (`diff` bez różnic). Nie jest to błąd, ale warto rozważyć, czy trzymanie dwóch identycznych plików ma sens, czy `LICENSE-BETA.txt` powinien odsyłać do `LICENSE.txt` zamiast dublować treść (żeby przy przyszłej zmianie nie trzeba było pamiętać o obu).

### **Realna niespójność — `LICENSE.pdf` jest przeterminowany**
`LICENSE.pdf` (i tylko ten plik) wciąż zawiera starą nazwę produktu: *"LICENCJA OTWARTA CLAUDE SAFE MODE FOR WORD"*, *"program Claude Safe Mode for Word"*, *"Claude Safe Mode"* w § 6 (znaki towarowe). `LICENSE.txt` i `LICENSE-BETA.txt` już poprawnie mówią o "CSM for Word" / "CSM".

To nie jest kosmetyka — `install-guide.html:88` aktywnie linkuje użytkownika do pobrania **właśnie tego** pliku PDF: `<a href="LICENSE.pdf" download>Pobierz licencję w PDF</a>`. Każdy klient/kontrahent, który pobierze licencję w PDF przy weryfikacji due-diligence, zobaczy nazwę produktu sprzed rebrandingu. `tests/selftest.py:576` sprawdza tylko `.exists()`, nie treść — dlatego automatyczne testy tego nie wyłapały.

**Do zrobienia przez Opusa**: wygenerować `LICENSE.pdf` na nowo z aktualnej treści `LICENSE.txt` (z nazwą "CSM for Word" / "CSM" wszędzie, łącznie z § 6 znaki towarowe). To pasuje do wcześniej zidentyfikowanego w pamięci projektu wzorca "docs renamed to CSM/CSMAddin in beta1 but scripts still use old paths" — kolejny artefakt zapomniany przy rebrandingu.

### Zależności zewnętrzne — potwierdzone niezależnie
- Clippit 3.4.3 (MIT) pinowany w `sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj` — potwierdzone, komentarz w kodzie ostrzega, że 3.5.x wymaga net10, więc nie podnosić bezmyślnie.
- `server/wheelhouse/` (18 paczek): fastapi, pydantic, uvicorn, starlette, lxml, click, h11, anyio itd. — wszystkie to standardowe pakiety z licencjami MIT/BSD. Potwierdzone przeglądem listy, zgodne z deklaracją.

### Rekomendacja dot. nazewnictwa (do decyzji biznesowej, nie wykonuję sam)
Nazwa pliku/tytuł "LICENCJA **OTWARTA** CSM" może być czytana przez odbiorców jako synonim "open source", mimo że licencja nie jest OSI-standard (obowiązek odsyłania modyfikacji do licencjodawcy, brak wolności takiej jak w MIT/GPL). Skoro decyzja to pozostanie przy obecnej licencji, sugeruję Opusowi dodać w `taskpane.html` (obok istniejącego `<details class="license-details">`) jedno zdanie zastrzeżenia: że to autorska licencja copyleft, nie standard OSI — to tani sposób na uniknięcie zarzutu wprowadzania w błąd bez zmiany samej licencji.

---

## 2. Precyzja i trafność pseudonimizacji

Zbudowałem i uruchomiłem dodatkowy, niezależny zestaw 24 syntetycznych przypadków (poza istniejącą siatką 16) celowo trafiających w kategorie, które oryginalny raport wskazał jako niepokryte: inicjały, zdrobnienia, powtórzone nazwiska, podwójne nazwiska, obce nazwiska, firmy JDG/CEIDG, formy PPHU, zagraniczne IBAN, odmienione nazwy sądów. Plik z przypadkami: `CSM_SONNET5_EXTENDED_BENCHMARK_CASES_2026-07-01.json` (ten sam katalog co ten raport) — format identyczny z `server/data/regression_cases/pseudonymization_mapping_grid_cases.json`, można go od razu podać do `tools/evaluate_pseudonymization_grid.py --cases <plik>` żeby odtworzyć wynik.

**Dobra wiadomość najpierw** — silnik poprawnie obsłużył (potwierdzone realnym zamaskowanym tekstem):
- Rozróżnienie dwojga osób o tym samym nazwisku różnej płci (Jan Kowalski / Anna Kowalska) bez pomylenia.
- Podwójne nazwisko po mężu (Anna Kowalska-Nowak).
- Nazwiska obcojęzyczne (John Smith, transliterowane Wołodymyr Kowalenko).
- Zdrobnienie odnoszące się do wcześniej wprowadzonej pełnej formy (Katarzyna Zielińska → "Kasią"/"Kasia").
- Trzy różne formy odmiany tego samego imienia i nazwiska w jednym dokumencie (Michał Adam Nowacki / Michała Adama Nowackiego / Michałowi Adamowi Nowackiemu) — wszystkie trzy poprawnie połączone.
- Formy spółek: `Kowalski, Nowak i Wspólnicy Sp.j.`, `BUDMEX Spółka z ograniczoną odpowiedzialnością Spółka komandytowa`, zagraniczna `Amazon EU Sarl`.
- Guard na fałszywe pozytywy: "Pan Kowal" (osoba) vs. "zawód kowal" (rzeczownik pospolity) — poprawnie rozróżnione.

To jest solidny fundament silnika — nie jest to "słaby" mechanizm, tylko ma konkretne, dające się nazwać dziury.

### Znalezione i zlokalizowane luki (precision/recall)

**A. Firmy jednoosobowe (JDG) w naturalnym sformułowaniu "prowadząc(y/a) działalność ... pod firmą/nazwą X" nie są wykrywane jako COMPANY — realny wyciek danych identyfikujących firmę.**

Dowód: tekst `"Anna Nowak, ..., prowadząca działalność pod nazwą ANNA NOWAK STUDIO GRAFICZNE."` → wynik maskowania: `"[PERSON_1], ..., prowadząca działalność pod nazwą [PERSON_1_ALIAS_1] STUDIO GRAFICZNE."` — fraza `STUDIO GRAFICZNE` zostaje w pełni jawna, doklejona bezpośrednio do placeholdera.

Przyczyna źródłowa: `server/redactor.py:575-576`, `SOLE_PROPRIETOR_LABEL_PATTERN`. Wzorzec wymaga formalnej etykiety przed dwukropkiem/myślnikiem: `przedsiębiorca`, `jednoosobowa działalność gospodarcza`, `JDG`, `osoba fizyczna prowadząca działalność gospodarczą` — **nie** obejmuje najpowszechniejszego sformułowania używanego w realnych pozwach: "[Imię Nazwisko] prowadząc-y/a działalność gospodarczą pod firmą/nazwą [FIRMA]" (dokładnie ta fraza, którą własne narzędzie kancelarii, easyEPU, generuje w treści pozwów — patrz pamięć projektu `easyepu_jdg_oznaczenie`). To nie jest teoretyczny brzegowy przypadek — to składnia, którą kancelaria sama produkuje w innych swoich dokumentach.

**Wytyczna dla Opusa**: dodać do `SOLE_PROPRIETOR_LABEL_PATTERN` (albo osobny wzorzec obok) alternatywną gałąź dopasowującą `(?:prowadząc(?:y|a)\s+działalność(?:\s+gospodarczą)?\s+pod\s+(?:firmą|nazwą)\s+)(?P<company>...)`, z tym samym przechwytywaniem grupy `company` co istniejący wzorzec. Dodać regresję do `server/data/regression_cases/pseudonymization_mapping_grid_cases.json` odzwierciedlającą dokładnie ten przypadek.

**B. Firmy z prefiksem typu P.P.H.U./F.H.U./P.H.U. (bardzo częste w polskich fakturach/umowach JDG) nie są rozpoznawane jako COMPANY w ogóle.**

Dowód: `"Sprzedawcą jest P.P.H.U. \"KOWEX\" Jan Kowalski z siedzibą w Krośnie."` → wynik: `Sprzedawcą jest P.P.H.U. "KOWEX" [PERSON_1] z siedzibą w [ADDRESS_SIEDZIBA_1].` — fraza `P.P.H.U. "KOWEX"` (nazwa handlowa) pozostaje w pełni jawna.

Przyczyna źródłowa: `ORG_PREFIX` w `server/redactor.py:145-149` zawiera ogólne słowa organizacyjne (fundacja, bank, kancelaria, firma...) ale nie zawiera powszechnych polskich skrótów działalności jednoosobowej: `P\.?P\.?H\.?U\.?`, `F\.?H\.?U\.?`, `P\.?H\.?U\.?`, `PPUH`. Bez tego prefiksu, cała reguła `COMPANY` (linia 211) nie dopasowuje frazy, bo nie ma po niej też typowego sufiksu (sp. z o.o. itd.).

**Wytyczna dla Opusa**: rozszerzyć `ORG_PREFIX` o warianty P.P.H.U./F.H.U./P.H.U./PPUH (z opcjonalnymi kropkami), z testem regresyjnym analogicznym do powyższego.

**C. Inicjały + nazwisko ("J. Kowalski") nie są wykrywane wcale.**

Dowód: `"W sprawie wystąpił J. Kowalski, ..."` → brak jakiegokolwiek maskowania, `replacements: []`. To dokładnie kategoria, którą poprzedni raport wymienił jako lukę do zamknięcia ("initials, abbreviated names") — teraz mam konkretny, odtwarzalny dowód pustego wyniku, a nie tylko przypuszczenie.

**Wytyczna dla Opusa**: znaleźć główny wzorzec PERSON (import osoby, prawdopodobnie okolice `PERSON_NAME_LOOSE` używanego też w JDG) i dodać wariant `[A-ZĄĆĘŁŃÓŚŹŻ]\.\s*[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+` (inicjał + nazwisko), pod kontrolą kontekstu żeby nie łapać skrótów typu "ul." czy "nr".

**D. Zagraniczne IBAN (nie-PL) nie są wykrywane.**

Dowód: niemiecki IBAN `DE89370400440532013000` → brak maskowania. Przyczyna: `server/redactor.py:192` (wzorzec `IBAN`) i linie 455/463 (`BANK_ACCOUNT_CONTEXT_PATTERN`, `BANK_ACCOUNT_OWNER_CONTEXT_PATTERN`) są zakodowane na sztywno pod polski NRB: albo prefiks `PL` + 26 cyfr, albo dokładnie 26 cyfr bez prefiksu. Format IBAN innych krajów ma inną długość (DE=22, FR=27, GB=22 itd.) i nie zostanie dopasowany żadną z tych trzech reguł.

**Wytyczna dla Opusa**: rozważyć ogólny wzorzec IBAN wg normy ISO 13616 (2 litery kraju + 2 cyfry kontrolne + 11–30 znaków alfanumerycznych, długość zależna od kraju) obok istniejącej, bardziej permisywnej reguły kontekstowej dla PL. Priorytet zależy od tego, jak często kancelaria obsługuje klientów zagranicznych/płatności transgraniczne — do potwierdzenia z użytkownikiem, ale sam brak jest bezsporny.

**E. Nazwa sądu w formie odmienionej (narzędnik: "Sądem Rejonowym w X") nie jest wykrywana — działa tylko forma mianownikowa.**

Dowód: oryginalna siatka 16 przypadków ma tylko `"Sąd Okręgowy w Rzeszowie"` (mianownik) i to działa. Mój przypadek z `"przed Sądem Rejonowym w Dębicy"` (narzędnik, bardzo częsty w pismach: "wnoszę przed Sądem...", "postępowanie przed Sądem...") nie został w ogóle zamaskowany.

**Wytyczna dla Opusa**: sprawdzić wzorzec COURT (okolice `server/redactor.py:1022-1067`, funkcja obsługująca skróty SR/SO/SA/SN) i dodać obsługę odmiany narzędnikowej/celownikowej nazwy sądu, analogicznie do istniejącej obsługi odmiany imion w `name_variants.py`.

**F. Samo nazwisko bez tytułu grzecznościowego na początku zdania ("Nowak złożył apelację...") nie jest wykrywane.**

To częsty styl w orzeczeniach/pismach przy drugim/trzecim odwołaniu do strony (po wcześniejszym wprowadzeniu pełnego imienia i nazwiska). Oryginalna siatka testowa ma przypadek `"Pani Mucha złożyła..."` (z tytułem) — działa. Bez tytułu — nie. To spójne z tym, co poprzedni raport już zaznaczył jako obszar do rozwoju ("repeated same-surname parties"), teraz potwierdzone konkretnym niepowodzeniem.

**Wytyczna dla Opusa**: to najtrudniejsza z luk do bezpiecznego naprawienia — rozpoznawanie gołego nazwiska bez kontekstu grzecznościowego niesie wysokie ryzyko fałszywych pozytywów (każde nazwisko będące też słowem pospolitym). Rekomenduję nie łatać tego generycznym wzorcem, tylko rozszerzyć istniejący mechanizm identity ledger/alias (silnik już śledzi warianty odmiany dla znanych imion i nazwisk w dokumencie) o dopasowywanie **tylko** nazwisk już wprowadzonych wcześniej w pełnej formie w tym samym dokumencie — czyli higienicznie bezpieczne rozszerzenie zasięgu już istniejącego mechanizmu identity ledger, a nie nowy ogólny wzorzec.

**G. Walidacja sumy kontrolnej PESEL — brak (niski priorytet, kierunek bezpieczny).**

`"99999999999"` (nieprawidłowy PESEL) po etykiecie "PESEL:" zostaje zamaskowany mimo nieprawidłowej struktury daty urodzenia w numerze. To nie jest luka bezpieczeństwa — kierunek błędu jest "nadmiarowo ostrożny", nie "nadmiarowo odsłaniający". Wspomniane też w pamięci projektu jako już rozpoznany, odłożony temat (checksum ID-card jako kandydat na v0.4). Rekomendacja: zostawić jako niski priorytet, ewentualnie połączyć z pracami nad "AInonymous inspirations" już odnotowanymi w backlogu.

### Rekomendacja co do zakresu benchmarku
Wynik 24 nowych przypadków: 16 PASS, 8 FAIL (3 z nich to błąd mojej specyfikacji testu — kategoria CONTRACTOR zamiast COMPANY, to nie błąd silnika — 5 to realne, potwierdzone luki A–F powyżej). To potwierdza tezę z pierwszego raportu: silnik jest dobry na to, co zostało już przetestowane, i ma niezmapowane dziury poza tym zakresem. Rekomenduję, żeby Opus po naprawieniu A–E dopisał te przypadki (i jeszcze z 20-30 kolejnych z tych samych rodzin: więcej wariantów JDG, więcej odmian nazw sądów, więcej formatów zagranicznych identyfikatorów) na stałe do `pseudonymization_mapping_grid_cases.json`, żeby te konkretne regresje nie wróciły.

---

## 3. UI dodawania/łączenia/zmiany typu nazw (mapping preview)

Nie mogłem przeprowadzić live-testu w rzeczywistym Wordzie (brak środowiska Office.js w tej sesji) — poniższe to analiza statyczna kodu `addin/taskpane.js` + `addin/taskpane.html`, wystarczająco jednoznaczna, żeby nie wymagać live-testu do wykrycia problemu.

### Potwierdzony, konkretny defekt: pole "Zmień typ" jest fizycznie niewidoczne dla użytkownika

`addin/taskpane.html:344`:
```html
<textarea id="manualCategory" class="hidden" aria-hidden="true"></textarea>
```

To pole przechowuje reguły zmiany kategorii (`category_overrides`) dodawane przyciskiem "Zmień typ" (`taskpane.js:1649-1653`). W przeciwieństwie do `manualAlways`, `manualNever`, `manualMerge` (widoczne textarea, które użytkownik może przejrzeć i ręcznie edytować), `manualCategory` ma `class="hidden" aria-hidden="true"` i nigdzie w kodzie JS nie jest odkrywane. Sprawdziłem to grepem po całym `taskpane.js` — nie ma żadnego toggle/`classList.remove("hidden")` dla tego elementu.

**Skutek dla użytkownika**: po kliknięciu "Zmień typ" i wpisaniu docelowej kategorii w oknie `window.prompt()`, reguła zostaje dodana — ale użytkownik nie ma żadnego sposobu zobaczenia listy aktualnie ustawionych reguł zmiany kategorii w panelu. Jedyny sposób ich przejrzenia to kliknięcie "Eksportuj TXT" i otwarcie pobranego pliku. Nie ma też przycisku usunięcia pojedynczej reguły (dla żadnej z czterech kategorii reguł zresztą — jest tylko zbiorcze "Wyczyść reguły", które czyści wszystko naraz).

To bezpośrednio odpowiada na pytanie użytkownika z punktu 4 zlecenia ("czy funkcjonalności... działają poprawnie") — technicznie dane trafiają poprawnie do backendu (testy `test_placeholder_merge_and_instruction.py` i pokrewne przechodzą), ale ścieżka UI dla zmiany kategorii jest częściowo "ślepa": działa, ale użytkownik nie widzi co zrobił.

### Drugi problem: walidacja przy wpisywaniu jest za słaba, za późna
- "Zmień typ" (`promptForManualCategory`, `taskpane.js:1622-1627`): pokazuje listę przykładowych kategorii jako **tekst w treści promptu**, ale nie waliduje wpisanej wartości względem tej listy — `normalizeManualCategory` tylko usuwa niedozwolone znaki i wielka literuje. Literówka ("PERSOM" zamiast "PERSON") tworzy cichą, nową, nieznaną kategorię bez ostrzeżenia.
- "Scal z..." (`promptForMergeTarget`, `taskpane.js:1629-1637`): waliduje tylko **kształt** wpisanej wartości (`^\[[A-Z0-9_]+\]$`), nie sprawdza, czy podany placeholder **faktycznie istnieje** w bieżącym podglądzie. Nieistniejący placeholder zostanie przyjęty i trafi do reguły merge, a błąd ujawni się dopiero po kliknięciu "Zastosuj reguły" (czyli po całym round-tripie do backendu) — zgodnie z dzisiejszym utwardzeniem backendu ("Invalid/unresolvable merge pairs now fail clearly"), więc nie zepsuje dokumentu, ale zmarnuje cykl użytkownika i da niejasny komunikat błędu zamiast natychmiastowej podpowiedzi przy wpisywaniu.

### Rekomendacja restrukturyzacji UI (zgodnie z prośbą o czytelniejszą strukturę)
Zamiast czterech osobnych, ręcznie edytowalnych pól tekstowych z własnym mini-DSL (`wartość => KATEGORIA`), sugeruję Opusowi:
1. Odkryć/przeprojektować `manualCategory` jako widoczną, czytelną listę (nie ukryte textarea) — każda reguła jako wiersz z wartością, docelową kategorią i przyciskiem "Usuń".
2. Zamienić `window.prompt()` na natywny `<select>` z listy `MANUAL_CATEGORY_OPTIONS` (`taskpane.js:1600-1602`) zamiast wolnego tekstu — eliminuje literówki u źródła.
3. Dla "Scal z...": zamienić prompt na `<select>` wypełniony wynikiem `mappingPreviewPlaceholders()` (funkcja już istnieje, `taskpane.js:1610-1620`) — użytkownik wybiera z listy, nie może wpisać nieistniejącego placeholdera.
4. Dodać przycisk "Usuń" per wiersz reguły w każdej z czterech kategorii (zawsze/nigdy/kategoria/scalanie), nie tylko zbiorcze "Wyczyść".
5. Zachować textarea + import/eksport TXT jako opcję "zaawansowaną" (np. w rozwijanym `<details>`) dla prawników, którzy wolą edytować hurtowo/przekazywać plik między sobą — to jest wartościowa funkcja, nie do usunięcia, tylko nie powinna być jedynym interfejsem.

---

## 4. Bezpieczeństwo / prywatność / gotowość komercjalizacyjna

Niezależnie zweryfikowałem (nie tylko odczytałem deklarację) kluczowe mechanizmy:

- **Token API**: `server/security.py:73-77`, porównanie przez `hmac.compare_digest` (odporne na timing attack) — potwierdzone, dobra praktyka.
- **CORS**: `server/api.py:508-524`, domyślnie tylko `https://localhost:3000` i `https://127.0.0.1:3000`, rozszerzalne przez `CSM_ALLOWED_ORIGINS` — potwierdzone jako zawężone, nie wildcard.
- **Odmowa bindowania na interfejsie wildcard**: `server/static_addin_server.py:90-108` — jawna lista zakazanych hostów (`0.0.0.0`, `::`, `*`) z komunikatem odmowy — potwierdzone w kodzie.
- **DPAPI dla map**: `server/redactor.py:2918-3057` — realna implementacja przez `ctypes` wołająca Windows `CryptProtectData`/`CryptUnprotectData` (nie tylko komentarz) — potwierdzone, z jawnym fallbackiem na kopertę plaintext na systemach nie-Windows (udokumentowane w kodzie, nie ukryte).
- **Skrypty VPS** (`tools/provision-vps.ps1`): tokeny/klucze API generowane losowo (`New-RandomToken`, 32 bajty), przekazywane przez zmienne środowiskowe do cloud-init, użytkownik jest jawnie ostrzegany na końcu ("WAZNE: Zapisz token API w bezpiecznym miejscu") — wygląda rozsądnie na pierwszy rzut oka, ale **nie przeprowadziłem tu pełnego osobnego audytu bezpieczeństwa** (obsługa kluczy dostawców VPS, Hetzner/IONOS) — to zgodnie z wcześniejszą rekomendacją wymaga odrębnego, dedykowanego przeglądu przed komercyjną ofertą wdrożenia w chmurze, nie robię tego "przy okazji".

### Potwierdzone jako wciąż nieobecne (sprawdzone bezpośrednio, nie na słowo)
- Brak jakiegokolwiek pliku SBOM / THIRD-PARTY-NOTICES w repo.
- Brak jakichkolwiek odniesień do `signtool`/code-signingu w `installer/` lub `tools/` — instalator nie jest podpisywany.
- Brak opublikowanej polityki prywatności i polityki zgłaszania podatności jako osobnych dokumentów w repo.

To są te same braki, które wskazał poprzedni raport — potwierdzam je jako realne i wciąż otwarte, nie zamknięte przez nikogo w międzyczasie.

---

## Podsumowanie priorytetów dla Opusa 4.8

Rekomendowana kolejność (od najwyższego realnego ryzyka/wartości):

1. **[Pseudonimizacja — wyciek danych]** Naprawić A (JDG "pod firmą/nazwą") i B (P.P.H.U./F.H.U./P.H.U.) w `server/redactor.py` — to realne, potwierdzone przypadki zostawiania nazwy firmy w jawnym tekście, bezpośrednio zgodne ze stylem dokumentów, które kancelaria sama produkuje.
2. **[UI — przejrzystość]** Odkryć/przeprojektować pole `manualCategory` (`addin/taskpane.html:344`) i zamienić prompty na `<select>` — użytkownik obecnie nie widzi własnych reguł zmiany kategorii.
3. **[Pseudonimizacja — recall]** Inicjały (C), odmiana nazwy sądu (E), zagraniczne IBAN (D) — w kolejności zależnej od tego, jak często takie dane pojawiają się w dokumentach kancelarii.
4. **[Licencja]** Odtworzyć `LICENSE.pdf` z aktualnej treści (nazwa CSM, nie Claude Safe Mode) — mały nakład, realne ryzyko wizerunkowe przy due diligence.
5. **[Formalności komercjalizacyjne]** SBOM, code-signing instalatora, polityka prywatności/zgłaszania podatności — zgodnie z wcześniejszą listą, bez zmian w priorytecie.
6. **[Pseudonimizacja — trudne]** Gołe nazwisko bez tytułu (F) — dopiero po rozszerzeniu identity ledger, nie generycznym wzorcem, ze względu na ryzyko fałszywych pozytywów.
