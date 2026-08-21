# CSM v1.0 — checklista testów Windows

Ta wersja jest iteracją źródłową. Nie trzeba budować instalatora po każdej iteracji, jeśli docelowo instalator ma powstać dopiero przy v1.0.

## Dodatkowe minimum dla v1.0

- [ ] Instalator pokazuje ekran licencji przed instalacją i nie pozwala kontynuować bez akceptacji.
- [ ] Projekt programu pomocniczego nadal targetuje `net8.0`, a nie preview/tymczasowe `net11.0`.
- [ ] `dotnet --info` pokazuje .NET 8 SDK.
- [ ] `dotnet restore sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj` kończy się sukcesem.
- [ ] `dotnet build sidecar/CSM.RevisionSidecar/CSM.RevisionSidecar.csproj -c Release` kończy się sukcesem.
- [ ] `dotnet test sidecar/CSM.RevisionSidecar.Tests/CSM.RevisionSidecar.Tests.csproj -c Release` kończy się sukcesem.
- [ ] Panel Worda pokazuje, że mechanizm zachowania śledzenia zmian jest gotowy.


## Test kontrolny panelu

1. Uruchom CSM z aktualnej paczki źródłowej.
2. Otwórz Word i panel CSM.
3. Potwierdź, że wersja widoczna w panelu/API to `1.0`.
4. Przygotuj dokument do Claude.
5. Otwórz sekcję „Kontrola mapowań i ręczne reguły v1.0”.
6. Kliknij „Pokaż mapowania lokalne”.
7. Potwierdź, że tabela pokazuje placeholder, kategorię, wartość lokalną i liczbę wystąpień.
8. Kliknij „Kopiuj mapowania TXT” i sprawdź zawartość schowka.
9. Kliknij „Pobierz mapowania JSON” i sprawdź, czy plik się pobiera.

## Test ręcznych reguł

1. W polu „Zawsze anonimizuj” wpisz przykładową frazę, która została pominięta.
2. W polu „Nigdy nie anonimizuj” wpisz fałszywy pozytyw.
3. Kliknij „Zastosuj reguły i utwórz nową kopię _CSM_anon”.
4. Sprawdź nowy dokument `_CSM_anon.docx`.
5. Sprawdź raport anonimizacji i nowy identyfikator mapy.

## Testy regresyjne

1. Sprawdź, czy rachunki bankowe nadal są anonimizowane.
2. Sprawdź, czy obrazy w DOCX nadal są zasłaniane w kopii `_CSM_anon`.
3. Sprawdź, czy licencja nie została zmieniona.


## Test reguł ręcznych v1.0

1. Utwórz kopię `_CSM_anon.docx`.
2. Otwórz sekcję „Kontrola mapowań i ręczne reguły v1.0”.
3. Dodaj przykładową frazę do „Zawsze anonimizuj”.
4. Kliknij „Zapisz reguły lokalnie”.
5. Wyczyść pola i kliknij „Wczytaj reguły lokalne”.
6. Sprawdź, czy reguły wróciły do pól.
7. Wyeksportuj reguły JSON i zaimportuj je ponownie.
8. Kliknij „Zastosuj reguły i utwórz nową kopię _CSM_anon”.
9. Sprawdź, czy powstała nowa mapa i nowy raport.
