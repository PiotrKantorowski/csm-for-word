# CSM v1.5 — checklista testów Windows

## Minimum dla v1.5

1. Uruchom panel CSM i sprawdź, że widoczna wersja to `v1.5`.
2. Przygotuj dokument testowy z danymi osobowymi i firmowymi.
3. Sprawdź, że numer PESEL z poprawną sumą kontrolną jest ukrywany, a losowa
   11-cyfrowa liczba bez etykiety "PESEL" (np. numer referencyjny zamówienia)
   zostaje jawna.
4. Sprawdź, że numer PESEL z etykietą "PESEL" w treści jest ukrywany zawsze,
   nawet gdy suma kontrolna się nie zgadza (np. literówka w dokumencie).
5. Na długim piśmie z wieloma stronami i wieloma osobami/firmami sprawdź,
   że maskowanie kończy się szybko i żadne dane nie zostają jawne.
6. Sprawdź wykrywanie firmy jednoosobowej w naturalnym sformułowaniu, np.
   `Jan Kowalski prowadzący działalność pod firmą Trans-Bud Jan Kowalski` —
   nazwa firmy nie może zostać jawna po anonimizacji.
7. Sprawdź wykrywanie firm z prefiksem `P.P.H.U.`, `F.H.U.`, `P.H.U.`, `PPUH`.
8. Sprawdź wykrywanie inicjału z nazwiskiem, np. `J. Kowalski`.
9. Sprawdź wykrywanie zagranicznego numeru IBAN (spoza Polski) obok polskiego NRB.
10. Sprawdź wykrywanie nazwy sądu w formie odmienionej, np.
    `przed Sądem Rejonowym w Rzeszowie`.
11. W panelu „Własne reguły ukrywania danych" dodaj regułę „Zmień typ" i sprawdź,
    że pojawia się jako czytelna pozycja na liście z możliwością usunięcia.
12. Przywróć dokument z mapy i sprawdź, że wersja jawna wraca poprawnie.
13. Sprawdź, że raporty `report_prepare.json` i `report_restore.json` są
    dostępne w katalogu sesji.

## Instalator

1. Zbuduj instalator poleceniem:
   `.\installer\build-csm-setup.ps1`
2. Uruchom `installer\output\CSM-Setup-v1.5.exe`.
3. Po instalacji otwórz Word i sprawdź, że dodatek CSM ładuje panel v1.5.

## Kryteria akceptacji

- PESEL bez etykiety maskowany tylko przy poprawnej sumie kontrolnej; PESEL
  z etykietą maskowany zawsze.
- Maskowanie długich pism z wieloma unikalnymi danymi osobowymi jest odczuwalnie
  szybsze niż w v1.4, bez zmiany wyników.
- Wzorce wykrywania z v1.4 (firma jednoosobowa, prefiksy P.P.H.U./F.H.U.,
  inicjał + nazwisko, zagraniczne IBAN, odmieniona nazwa sądu) wciąż działają.
- Mechanizm przywracania wersji jawnej nie został zmieniony.
- Testy automatyczne przechodzą lokalnie.
