# CSM rc17 stable panel rollback / fix

## Co zostalo naprawione

Poprzedni hotfix panelu wprowadzil blad rekurencji w globalnych handlerach JavaScript.
W pliku `taskpane.js` pojawily sie wczesne przypisania w stylu:

```js
window.v4PrepareDocxCopy = function CSM_v4PrepareEarly() {
  return v4PrepareDocxCopy.apply(this, arguments);
};
```

W klasycznym skrypcie przegladarkowym globalna deklaracja funkcji i wlasciwosc `window` sa ze soba powiazane.
Przypisanie do `window.v4PrepareDocxCopy` nadpisalo globalne wiazanie `v4PrepareDocxCopy` wrapperem, a wrapper wolal potem sam siebie.
Efekt w Word/WebView2: `btnV4Prepare: Maximum call stack size exceeded`.

Ta paczka cofa ten wadliwy fragment i wraca do stabilnego modelu:

- brak wczesnych wrapperow `CSM_*Early`,
- wiazanie przyciskow po `Office.onReady()`,
- eksport funkcji do `window` dopiero po zadeklarowaniu realnych funkcji,
- pozostaje automatyczne zamykanie taskpane po udanym prepare/restore,
- pozostaja poprawki backendu: zamykanie dokumentow COM, nadpisywanie oryginalu i autorzy Track Changes.

## Dlaczego nie ma setup.exe

Nie dolaczono gotowego instalatora EXE, zeby nie powtorzyc problemu ze starym / nieprzebudowanym instalatorem.
Do aktualizacji istniejacej instalacji uzyj:

```bat
tools\PATCH-INSTALLED-CSM-STABLE.cmd
```

Nowy instalator EXE trzeba zbudowac na Windows z Inno Setup z tych zrodel.

## Jak testowac

1. Uruchom `tools\PATCH-INSTALLED-CSM-STABLE.cmd` jako administrator.
2. Poczekaj, az skrypt zatrzyma CSM, zamknie Worda, skopiuje pliki i ponownie uruchomi CSM.
3. Otworz Worda dopiero po zakonczeniu skryptu.
4. Sprawdz START/STOP oraz prepare/restore.

