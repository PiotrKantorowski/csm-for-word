# CSM v1.4 — checklista testów Windows

## Minimum dla v1.4

1. Uruchom panel CSM i sprawdź, że widoczna wersja to `v1.4`.
2. Przygotuj dokument testowy z danymi osobowymi i firmowymi.
3. Sprawdź wykrywanie firmy jednoosobowej w naturalnym sformułowaniu, np.
   `Jan Kowalski prowadzący działalność pod firmą Trans-Bud Jan Kowalski` —
   nazwa firmy nie może zostać jawna po anonimizacji.
4. Sprawdź wykrywanie firm z prefiksem `P.P.H.U.`, `F.H.U.`, `P.H.U.`, `PPUH`.
5. Sprawdź wykrywanie inicjału z nazwiskiem, np. `J. Kowalski`.
6. Sprawdź wykrywanie zagranicznego numeru IBAN (spoza Polski) obok polskiego NRB.
7. Sprawdź wykrywanie nazwy sądu w formie odmienionej, np.
   `przed Sądem Rejonowym w Rzeszowie`.
8. W panelu „Własne reguły ukrywania danych" dodaj regułę „Zmień typ" i sprawdź,
   że pojawia się jako czytelna pozycja na liście z możliwością usunięcia.
9. Sprawdź, że „Zmień typ" i „Scal z..." korzystają z list wyboru, a nie z okien
   tekstowych `prompt`.
10. Sprawdź, że import/eksport reguł TXT działa jak wcześniej (sekcja zaawansowana).
11. Otwórz `LICENSE.pdf` i sprawdź, że nazwa produktu to `CSM for Word`
    (bez starej nazwy „Claude Safe Mode for Word").
12. Przywróć dokument z mapy i sprawdź, że wersja jawna wraca poprawnie.
13. Sprawdź, że raporty `report_prepare.json` i `report_restore.json` są
    dostępne w katalogu sesji.

## Instalator

1. Zbuduj instalator poleceniem:
   `.\installer\build-csm-setup.ps1`
2. Uruchom `installer\output\CSM-Setup-v1.4.exe`.
3. Po instalacji otwórz Word i sprawdź, że dodatek CSM ładuje panel v1.4.

## Kryteria akceptacji

- Nowe wzorce wykrywania (firma jednoosobowa, prefiksy P.P.H.U./F.H.U.,
  inicjał + nazwisko, zagraniczne IBAN, odmieniona nazwa sądu) działają.
- Panel własnych reguł pokazuje regułę zmiany typu jako czytelną, usuwalną pozycję.
- Mechanizm przywracania wersji jawnej nie został zmieniony.
- Testy automatyczne przechodzą lokalnie.
