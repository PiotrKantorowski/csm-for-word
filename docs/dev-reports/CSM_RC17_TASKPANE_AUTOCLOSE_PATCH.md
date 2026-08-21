# CSM rc17 — taskpane auto-close patch

## Cel zmiany

Po operacjach, w których backend zamyka dokument Worda przez COM, panel CSM przypięty do zamykanego dokumentu ma zamknąć się automatycznie. Dzięki temu użytkownik nie widzi starego panelu po zamknięciu pliku ani mylących błędów typu `signal is aborted without reason` / brak połączenia z lokalnym silnikiem CSM w nieaktualnym WebView2.

## Zakres

Zmieniono wyłącznie zachowanie operacyjne panelu. UI / wygląd nie był zmieniany.

## Zmiany w `addin/taskpane.js`

Dodano helpery:

- `closeCsmTaskpane(reason)` — best-effort zamykanie kontenera dodatku przez `Office.context.ui.closeContainer()`, z fallbackiem na `window.close()`.
- `closeCsmTaskpaneSoon(reason, delayMs)` — jednorazowe, lekko opóźnione zamknięcie panelu, żeby zdążył zapisać status i nie wykonać kilku zamknięć naraz.

Wywołania dodano po udanym:

1. `v4PrepareDocxCopy()` — gdy backend otworzył `_CSM_anon.docx` i zamyka oryginał.
2. `v4RestoreDocxCopy()` — gdy backend otworzył wersję jawną i zamyka `_CSM_anon.docx`.
3. `v4RestoreManualDocxCopy()` — gdy ręczny restore został wykonany z panelu otwartego przy pliku anon.

## Testy

Dodano test kontraktowy:

- `test_taskpane_closes_after_server_side_document_close`

Sprawdza, że panel używa `Office.context.ui.closeContainer()` oraz że auto-close jest wywoływany po prepare, restore i ręcznym restore.

## Walidacja wykonana w sandboxie

```text
python3 -m py_compile server/api.py server/tc_engine.py server/redactor.py server/security.py server/word_revision_engine.py  OK
node --check addin/taskpane.js                                                                            OK
node addin/scripts/validate-static.js                                                                     OK
pytest -q [krytyczne testy prepare/restore/path/TC/manual/context]                                        50 passed
```

## Uwaga testowa

Realne zamknięcie kontenera `Office.context.ui.closeContainer()` trzeba jeszcze potwierdzić na Windows 11 + Word + WebView2, bo sandbox Linux nie uruchamia hosta Office.
