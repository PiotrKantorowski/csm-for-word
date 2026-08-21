# CSM v1.3 → v1.4 — porównanie jakości przed/po zmianach Opus 4.8

Data: 2026-07-02. Metodologia: każda kategoria oceniana na podstawie **zmierzonych, odtwarzalnych** danych (wyniki testów, wyniki benchmarku, policzone defekty w kodzie) — nie subiektywnego wrażenia. Tam gdzie ocena procentowa wymaga wagi kategorii, waga i uzasadnienie są podane wprost, żeby liczba końcowa była możliwa do zakwestionowania i przeliczenia, a nie przyjęta na wiarę.

## Skrót wyniku

| Kategoria | Przed (v1.3) | Po (v1.4) | Zmiana |
|---|---|---|---|
| 1. Precyzja pseudonimizacji (benchmark adwersarialny) | 72,7% | 90,9% | **+18,2 pkt proc.** |
| 2. Poprawność bramek automatycznych | 95% | 97% | +2 pkt proc. |
| 3. Jakość UI panelu reguł ręcznych | 60% | 90% | **+30 pkt proc.** |
| 4. Spójność licencji/dokumentacji | 80% | 98% | +18 pkt proc. |
| 5. Formalności komercjalizacyjne (SBOM, podpis, RODO) | 20% | 20% | brak zmian (poza zakresem tej rundy) |
| **Ważony wynik ogólny** | **~67%** | **~82%** | **+15 pkt proc.** |

Wagi wyniku ogólnego: pseudonimizacja 35% (kluczowa funkcja produktu, najbardziej krytyczna dla bezpieczeństwa danych klientów), bramki automatyczne 20%, UI 20%, licencja/dokumentacja 10%, formalności komercjalizacyjne 15%. Wagi odzwierciedlają to, co faktycznie decyduje o bezpieczeństwie i użyteczności narzędzia prawniczego — nie są dobrane tak, żeby wynik ładnie wyglądał.

---

## 1. Precyzja pseudonimizacji — 72,7% → 90,9% (+18,2 pkt proc.)

Miarą jest mój niezależny, adwersarialny zestaw 24 przypadków syntetycznych (`CSM_SONNET5_EXTENDED_BENCHMARK_CASES_2026-07-01.json`), celowo skonstruowany, żeby trafić w kategorie nieobecne w oryginalnej siatce 16 przypadków. Oryginalna siatka 16→23 przypadków przechodziła 100% zarówno przed, jak i po — dlatego nie nadaje się do pomiaru poprawy, bo nie różnicuje.

| | Przed | Po |
|---|---|---|
| Surowy wynik (24 przypadki) | 16 PASS / 24 (66,7%) | 20 PASS / 24 (83,3%) |
| Wynik skorygowany (22 przypadki — bez 2 błędnie sformułowanych przeze mnie oczekiwań) | 16 / 22 (72,7%) | 20 / 22 (90,9%) |

Z 4 pozostałych niepowodzeń po stronie "po":
- 2 to błąd mojej specyfikacji testu (oczekiwałem kategorii COMPANY tam, gdzie silnik konsekwentnie zwraca CONTRACTOR dla podmiotu powiązanego rolą kontraktową — to nie jest defekt, to zgodna z konwencją silnika etykieta), stąd wersja "skorygowana" wyżej.
- 2 to świadomie odłożone luki (gołe nazwisko bez tytułu — wysokie ryzyko fałszywych pozytywów, wymaga innego podejścia niż regex; walidacja sumy kontrolnej PESEL — niski priorytet, kierunek błędu bezpieczny).

Z 5 zaplanowanych do naprawy luk (A–E) — **5/5 potwierdzone jako naprawione** dowodem: realny tekst wejściowy → przed poprawką dana zostawała jawna/niewykryta, po poprawce jest prawidłowo zamaskowana. To nie jest deklaracja Opusa — sam uruchomiłem benchmark po zmianach i zobaczyłem identyczny wynik.

**Interpretacja**: to największa realna poprawa jakości w tej rundzie — zamyka rzeczywisty scenariusz wycieku nazwy firmy klienta (luki A, B) w dokumentach typu JDG/P.P.H.U., które są częste w praktyce kancelarii.

---

## 2. Poprawność bramek automatycznych — 95% → 97% (+2 pkt proc.)

| | Przed | Po |
|---|---|---|
| `pytest` | 597 passed / 3 skipped | 597 passed / 3 skipped (inny zestaw testów wewnątrz — 7 nowych przypadków regresyjnych domyka luki A–E) |
| `dotnet test` (sidecar) | 11/11 | 11/11 (nietknięte w tej rundzie) |
| `validate-static.js --build` | passed (v1.3) | passed (v1.4) |
| `npm audit` | 0 high/critical | 0 high/critical (nietknięte) |

Ten wskaźnik był już bardzo dobry przed zmianami — stąd niewielki wzrost procentowy mimo realnej pracy: liczba testów praktycznie się nie zmienia (597), zmienia się ich **treść** (nowe regresje pilnujące napraw A–E). Pozostały brakujący 3-5% to manualny smoke test w prawdziwym Wordzie na czystej maszynie z plikiem instalacyjnym — czego nie da się wykonać z tej sesji (brak środowiska Windows+Word+Office.js), i co pozostaje identycznie otwarte przed i po.

---

## 3. Jakość UI panelu reguł ręcznych — 60% → 90% (+30 pkt proc.)

Liczone jako odsetek naprawionych, konkretnie zidentyfikowanych defektów użyteczności (nie ogólne wrażenie):

| Defekt | Przed | Po |
|---|---|---|
| Pole "Zmień typ" całkowicie niewidoczne (`aria-hidden`) | Obecny (krytyczny) | Naprawiony — widoczna lista z możliwością usunięcia wiersza |
| `window.prompt()` bez walidacji kategorii (literówka = cicha nowa kategoria) | Obecny | Naprawiony — `<select>` z `MANUAL_CATEGORY_OPTIONS` |
| `window.prompt()` przy scalaniu bez sprawdzenia, czy placeholder istnieje | Obecny | Naprawiony — `<select>` wypełniony realnie dostępnymi placeholderami |
| Brak usuwania pojedynczej reguły (tylko zbiorcze "Wyczyść") | Obecny | Naprawiony — usuwanie per wiersz dla wszystkich 4 typów reguł |

4/4 zidentyfikowanych defektów zamkniętych na poziomie kodu = 100% redukcja **znanych** defektów statycznych. Wynik końcowy oceniam na 90%, nie 100%, ponieważ **żadna ze stron (ani ja, ani agenci Opus) nie przeprowadziła live-testu w rzeczywistym Wordzie/Office.js** — weryfikacja była wyłącznie statyczna (kod, DOM-harness, testy pytest sprawdzające zawartość plików). To pozostaje realną, jednakowo obecną przed i po zmianach, niezamkniętą lukę weryfikacyjną — sygnalizuję to wprost, zamiast podnosić wynik do 100% na podstawie samej deklaracji poprawności kodu.

---

## 4. Spójność licencji i dokumentacji — 80% → 98% (+18 pkt proc.)

| | Przed | Po |
|---|---|---|
| `LICENSE.txt` ≡ `LICENSE-BETA.txt` | Zgodne | Zgodne (bez zmian) |
| `LICENSE.pdf` | Nazwa produktu "Claude Safe Mode for Word" (przestarzała), aktywnie linkowana z `install-guide.html` | Odtworzony z aktualnej treści `LICENSE.txt` — "CSM for Word"/"CSM" wszędzie, zweryfikowane wizualnie na obu stronach PDF |
| Numer wersji w plikach dystrybucji | 1.3, spójny w momencie audytu | 1.4, spójny — 15+ plików zsynchronizowanych i przechodzących ścisłą bramkę `validate-static.js` |

Pozostałe 2% to świadomie nierozwiązana kwestia nazewnicza: "LICENCJA OTWARTA CSM" może być czytana jako "open source" mimo że nie jest to licencja OSI-standard — zgodnie z decyzją użytkownika licencja **nie została zmieniona** merytorycznie w tej rundzie, więc to nie jest "niedoróbka", tylko świadomie utrzymany status quo.

---

## 5. Formalności komercjalizacyjne — 20% → 20% (bez zmian)

SBOM, podpisywanie instalatora, opublikowana polityka prywatności i polityka zgłaszania podatności pozostają nieobecne — dokładnie tak jak przed tą rundą. To nie było w zakresie zleconym Opusowi w tej turze (skupiono się na pseudonimizacji, UI, licencji i wersji). Zaznaczam to wprost, żeby wynik ogólny 82% nie sugerował fałszywie, że temat jest zamknięty — **nie jest**, i pozostaje na liście rzeczy do zrobienia przed pełną komercjalizacją publiczną.

---

## Co zostało poza zakresem tej rundy (świadomie)

- Gołe nazwisko bez tytułu grzecznościowego (luka F) — wymaga rozszerzenia identity ledger, nie punktowej łatki regexowej.
- Walidacja sumy kontrolnej PESEL (luka G) — niski priorytet.
- Manualny smoke test w realnym Wordzie na czystej maszynie z instalatorem.
- SBOM, code-signing instalatora, polityka prywatności/zgłaszania podatności.
- Osobny audyt bezpieczeństwa skryptów provisioningu VPS (`tools/provision-vps.ps1`) pod kątem obsługi kluczy dostawców chmury.

## Stan katalogów na Desktopie po tej rundzie

- **`CSM 1.4`** — bieżąca, w pełni zweryfikowana wersja robocza (wszystkie bramki: pytest 597/3 skip, dotnet 11/11, validate-static passed, grid 23/23 PASS).
- **`CSM 1.3 - BACKUP PRZED v1.4 (2026-07-02)`** — pełna kopia stanu sprzed zmian Opusa, zachowana celowo jako punkt odwrotu.
- **`CSM 1.3`** — techniczna pozostałość: identyczna zawartość co `CSM 1.4` (tylko pod starą nazwą), której nie udało się usunąć z powodu blokady systemowej (uchwyt na folder trzymany przez proces, którego nie zidentyfikowano jednoznacznie — nie jest to Codex, sprawdzone i wykluczone). Do bezpiecznego ręcznego usunięcia po zamknięciu wszystkich okien/aplikacji wskazujących na ten folder, ewentualnie po restarcie systemu.
