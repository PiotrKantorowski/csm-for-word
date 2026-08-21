# CSM v1.6 — checklista testów Windows

## Minimum dla v1.6 (reguły ręczne)

1. Uruchom panel CSM i sprawdź, że widoczna wersja to `v1.6`.
2. Przygotuj dokument testowy z danymi osobowymi i firmowymi, w tym co najmniej
   jednym poprawnym numerem PESEL i osobą wymienioną w kilku przypadkach
   (np. `Zenon Kowalski` i `Zenonowi Kowalskiemu`).
3. Granice słów: dodaj regułę „zawsze ukrywaj" z krótką frazą będącą częścią
   dłuższego słowa (np. `Ala` przy obecnym w tekście `otrzymała`) i sprawdź,
   że środek słowa nie został zamaskowany.
4. Odmiana: dodaj regułę `Zenon Kowalski => OSOBA` i sprawdź, że po remasku
   ukryte są także formy odmienione oraz że wszystkie trafiły do jednej rodziny
   placeholderów `[OSOBA_n]` (bez osobnego `[MANUAL_n]`).
5. Ochrona danych z sumą kontrolną: dodaj regułę „nie ukrywaj" z pełnym numerem
   PESEL bez prefiksu `!` — PESEL ma pozostać ukryty, a panel ma pokazać
   ostrzeżenie. Następnie powtórz z prefiksem `!` — PESEL ma zostać jawny.
6. Podgląd skutków: przed zastosowaniem reguł kliknij „Podgląd skutków reguł
   (bez zmian w plikach)" i sprawdź, że pokazuje liczbę dopasowań reguł
   „zawsze", wyłączane wykrycia reguł „nigdy" z kontekstem oraz reguły bez
   efektu; żaden plik nie może się zmienić.
7. Poziomy zapisu: wpisz nazwę w polu „Klient / sprawa", zapisz reguły dla
   klienta, wyczyść reguły w panelu i wykonaj anonimizację — zapisane reguły
   klienta mają zostać dołączone automatycznie (sekcja „Skuteczność reguł").
8. Zapis dla kancelarii: zapisz regułę dla kancelarii (np. nazwa własnej
   kancelarii w „nie ukrywaj") i sprawdź, że działa przy dokumencie innego
   klienta.
9. Rozliczalność: po anonimizacji sprawdź w panelu sekcję „Skuteczność reguł"
   oraz pola `controls_effects` i `saved_rules` w `report_prepare.json`.
10. Okno „wątpliwe elementy": zaznacz element, zaznacz opcję zapisu jako stałe
    reguły klienta i sprawdź, że reguła pojawia się w zapisanych regułach
    klienta („Pokaż zapisane reguły").
11. Regresja v1.5: PESEL bez etykiety maskowany tylko przy poprawnej sumie
    kontrolnej; PESEL z etykietą maskowany zawsze; długie pisma maskują się
    szybko.
12. Przywróć dokument z mapy i sprawdź, że wersja jawna wraca poprawnie.
13. Sprawdź, że raporty `report_prepare.json` i `report_restore.json` są
    dostępne w katalogu sesji.

## Instalator

1. Zbuduj instalator poleceniem:
   `.\installer\build-csm-setup.ps1`
2. Uruchom `installer\output\CSM-Setup-v1.6.exe`.
3. Po instalacji otwórz Word i sprawdź, że dodatek CSM ładuje panel v1.6.

## Kryteria akceptacji

- Reguły ręczne dopasowują w granicach słów; reguła „nigdy" nie odsłania danych
  z sumą kontrolną bez jawnego wymuszenia (`!`).
- Reguła „zawsze" z kategorią OSOBA/FIRMA/SAD obejmuje odmiany i klastruje się
  z wykryciami automatycznymi.
- Podgląd skutków reguł działa bez tworzenia plików; po anonimizacji panel
  pokazuje rozliczalność reguł (w tym reguły martwe).
- Reguły zapisane dla klienta i kancelarii są dołączane automatycznie i
  przechowywane lokalnie w postaci zaszyfrowanej.
- Wzorce wykrywania z v1.4 i v1.5 wciąż działają.
- Mechanizm przywracania wersji jawnej nie został zmieniony.
- Testy automatyczne przechodzą lokalnie.
