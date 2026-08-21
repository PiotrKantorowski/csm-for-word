# CSM for Word v1.6 — instalacja i start

## Instalacja

1. Rozpakuj całą paczkę do dowolnego folderu tymczasowego.
2. Kliknij dwukrotnie `ZAINSTALUJ_CSM.cmd`.
3. Jeśli Windows pokaże pytanie UAC, wybierz **Tak**.
4. Instalator sam skopiuje CSM do `C:\CSM`, skonfiguruje Worda, wyczyści cache dodatku, utworzy jedną ikonę **CSM** na pulpicie i włączy autostart lokalnych usług CSM po zalogowaniu użytkownika.

Nie uruchamiaj ręcznie skryptów technicznych z katalogu `tools` — są używane automatycznie przez instalator i panel CSM.

## Codzienna praca

Po instalacji CSM powinien startować automatycznie po zalogowaniu do Windows. W typowym użyciu nie trzeba codziennie klikać START.

Na pulpicie zostaje jedna ikona:

```txt
CSM
```

Panel CSM jest teraz panelem serwisowym i pozwala wykonać:

```txt
START — awaryjnie uruchom CSM w tle
STOP — zatrzymaj CSM
CLEAN — wyczyść cache Worda
NAPRAW — odśwież instalację
ODINSTALUJ — usuń CSM
```

Jeśli chcesz użyć lokalnego Bielika jako dodatkowego detektora danych do anonimizacji, uruchom lokalny model przez Ollama albo llama.cpp/LM Studio, a potem wybierz w panelu **START + BIELIK**. Szczegóły są w `docs\BIELIK-LOCAL-DETECTOR.md`.

Po wybraniu **START** lokalny silnik działa w tle. Okno panelu można zamknąć, a CSM nadal będzie dostępny dla dodatku w Wordzie. Zatrzymanie następuje dopiero po wybraniu **STOP**.

## Tryb negocjacyjny DOCX

W Wordzie używaj głównego trybu:

```txt
Utwórz i otwórz kopię do pracy z Claude
Utwórz i otwórz wersję jawną
```

CSM sam tworzy pliki robocze w tle i próbuje otwierać je w Wordzie. Użytkownik nie musi ręcznie wybierać ani pobierać plików w głównym flow.

## Automatyczne otwieranie panelu w kopii roboczej

Manifest dodatku wskazuje `Office.AutoShowTaskpaneWithDocument`, a frontend zapisuje w dokumencie ustawienie `Office.AutoShowTaskpaneWithDocument = true`. Dzięki temu Word może automatycznie otworzyć panel CSM po ponownym otwarciu dokumentu roboczego, o ile dodatek CSM jest już zainstalowany u użytkownika.

## Jak czytać raport anonimizacji

Po utworzeniu pliku `_CSM_anon.docx` panel Word pokazuje **Podsumowanie pseudonimizacji**. Najważniejsze pola:

```txt
unikalne wartości — ile różnych wartości CSM zastąpił placeholderami;
pozycje do kontroli — ile ostrzeżeń albo potencjalnych pozostałości wymaga ręcznej kontroli;
kategorie danych — typy wykrytych danych, np. PERSON, COMPANY, PESEL, ADDRESS;
ryzyka pozostałe — klasy danych, które mogą wymagać sprawdzenia w dokumencie;
zakres DOCX — które części pliku były analizowane, np. treść, nagłówki, stopki, komentarze, metadane.
```

Raport nie zawiera surowych podejrzanych danych, aby sam nie stał się źródłem wycieku. Kopia raportu jest zapisywana w folderze sesji jako `report_prepare.json`. Po przywróceniu wersji jawnej CSM zapisuje również `report_restore.json`. W panelu Word można skopiować raport do schowka albo pobrać go jako JSON.


## Ręczne reguły

W panelu CSM możesz po anonimizacji przejrzeć lokalne mapowania, dodać frazy do listy „zawsze anonimizuj”, wskazać frazy „nigdy nie anonimizuj”, zmienić kategorię oraz scalić placeholdery, np. `[OSOBA_8] => [OSOBA_3]`. Po zastosowaniu reguł CSM tworzy nową kopię `_CSM_anon.docx` z oryginalnego snapshotu sesji.

### Scalanie placeholderów

Użyj, gdy ta sama osoba lub firma została rozpoznana jako dwa różne byty, np. odmiana nazwiska, inicjał albo alias. Wpisuj jedną parę w linii: `SOURCE => TARGET`, np. `[OSOBA_8] => [OSOBA_3]`.
