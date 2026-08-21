# CSM v1.3 — checklista testów Windows

## Minimum dla v1.3

1. Uruchom panel CSM i sprawdź, że widoczna wersja to `v1.3`.
2. Przygotuj dokument testowy z danymi osobowymi i firmowymi.
3. Sprawdź, że standardowe przygotowanie dokumentu nie uruchamia Bielik
   automatycznie.
4. Włącz lekką kontrolę po anonimizacji i sprawdź, że raport pokazuje
   potencjalne pozostałości.
5. Uruchom głębszą kontrolę Bielik ręcznie i sprawdź, że wynik trafia do raportu.
6. Sprawdź dokument zawierający:
   `Kancelaria Prawna Kantorowski, Głąb i Wspólnicy Sp. j.`
7. Powtórz punkt 6 dla innej formy prawnej oraz dla wariantu bez formy prawnej.
8. Zweryfikuj, że po anonimizacji w treści nie zostaje `Kantorowski` ani `Głąb`.
9. Przywróć dokument z mapy i sprawdź, że wersja jawna wraca poprawnie.
10. Sprawdź, że raporty `report_prepare.json` i `report_restore.json` są
    dostępne w katalogu sesji.

## Instalator

1. Zbuduj instalator poleceniem:
   `.\installer\build-csm-setup.ps1`
2. Uruchom `installer\output\CSM-Setup-v1.3.exe`.
3. Po instalacji otwórz Word i sprawdź, że dodatek CSM ładuje panel v1.3.

## Kryteria akceptacji

- Dokument można przygotować i przywrócić bez zmiany zasad mapowania.
- Tryb Bielik jest uruchamiany tylko po świadomym wyborze użytkownika.
- Kancelaria KGL jest ukrywana jako podmiot także przy wariantach formy prawnej.
- Testy automatyczne przechodzą lokalnie.
