# CSM v0.6.1 rc12 — wytyczne dla Claude Code po audycie rc11 Windows-tested-with-failures

## Cel

Doprowadzić CSM do finalnego `v0.6.1`, bez przeskakiwania do `0.7`. Obecny etap to stabilizacja instalacji, wheelhouse, certyfikatu, sidecara i odwracalnej pseudonimizacji. `0.7` powinno zacząć się dopiero po zamknięciu finalnego `0.6.1` i potwierdzeniu działania u użytkowników.

## Wejście

Pracuj na paczce źródłowej `CSM_v0_6_1_rc12_ci_sidecar_exe_source.zip` albo na jej rozpakowanym katalogu.

W rc12 poprawiono workflow GitHub Actions: test integracyjny sidecara ma używać skompilowanego `CSM.RevisionSidecar.exe`, a nie `dotnet run`, ponieważ w raporcie rc11 `dotnet run` powodował fałszywe błędy 503 przy wolnym starcie procesu.

## Zadania obowiązkowe

### 1. Odbuduj sidecar i instalator

Uruchom na Windowsie:

```powershell
dotnet --info
dotnet restore sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj
dotnet build sidecar\CSM.RevisionSidecar\CSM.RevisionSidecar.csproj -c Release
dotnet test sidecar\CSM.RevisionSidecar.Tests\CSM.RevisionSidecar.Tests.csproj -c Release

$env:CSM_REVISION_SIDECAR_CMD = "$PWD\sidecar\CSM.RevisionSidecar\bin\Release\net8.0\CSM.RevisionSidecar.exe"
python -m pytest -q tests\test_revision_sidecar_integration.py

.\installer\build-csm-setup.ps1
```

DoD:

- `dotnet build` ma mieć 0 błędów.
- `dotnet test` ma mieć 0 failed, 0 skipped.
- `tests\test_revision_sidecar_integration.py` ma mieć 8/8 passed przy użyciu EXE, nie `dotnet run`.
- Powstaje `installer\output\CSM-Setup-v0.6.1.exe`.
- Raport zawiera SHA-256 EXE i SHA-256 finalnego ZIP-a. SHA w raporcie musi zgadzać się z realnymi plikami.

### 2. Wykonaj test instalatora GUI, nie tylko silent install

Uruchom normalnie:

```powershell
installer\output\CSM-Setup-v0.6.1.exe
```

Sprawdź ręcznie:

- ekran licencji jest widoczny,
- bez akceptacji licencji nie da się kontynuować,
- po akceptacji instalator nie zawiesza się na końcu,
- użytkownik widzi zakończenie instalacji,
- po instalacji istnieją logi:
  - `%TEMP%\CSM-install.log`,
  - `%TEMP%\CSM-setup-once.log`.

DoD:

- brak ukrytego pytania `AKCEPTUJE` w tle,
- brak zawieszenia prawie na końcu paska,
- błędy instalacyjne kończą się widocznym komunikatem i logiem, a nie ciszą.

### 3. Test clean install

Na czystym profilu użytkownika lub VM bez CSM:

1. Uruchom instalator GUI.
2. Po instalacji uruchom `C:\CSM\tools\CSM-DIAGNOZA.cmd`.
3. Sprawdź:

```powershell
Test-Path C:\CSM\server\.venv\Scripts\python.exe
& C:\CSM\server\.venv\Scripts\python.exe -c "import fastapi, uvicorn, pydantic, lxml.etree; print('imports ok')"
Invoke-WebRequest http://127.0.0.1:8787/health -UseBasicParsing
Invoke-WebRequest https://localhost:3000/taskpane.html -UseBasicParsing
```

DoD:

- `.venv` istnieje,
- importy Python przechodzą,
- backend działa na 8787 i zwraca `version: 0.6.1`,
- HTTPS add-in działa na 3000,
- certyfikat localhost ma `trusted=True` w diagnostyce,
- panel w Wordzie pokazuje `v0.6.1 — rc12` albo finalne `v0.6.1`, zależnie od decyzji wydawniczej.

### 4. Test upgrade/repair z 0.5 final2/final6

To jest blocker finalnego 0.6. Zasymuluj lub użyj realnej instalacji starego CSM 0.5/final2/final6.

Stan wejściowy powinien obejmować możliwie dużo starych elementów:

- stare `C:\CSM`,
- stare cache Worda,
- stary manifest i share `\\localhost\ClaudeSafeModeAddin\`,
- brak certyfikatu albo certyfikat istnieje, ale `trusted=False`,
- uszkodzone albo niepełne `.venv`,
- stare wpisy `0.5.0`, `final2`, `final6`, `20260516-final6` w plikach lub cache.

Uruchom instalator rc12/final 0.6 i sprawdź diagnostyką.

DoD:

- instalator naprawia `.venv`,
- instaluje zależności z `server\wheelhouse` bez potrzeby PyPI,
- naprawia certyfikat localhost,
- czyści cache Worda,
- backend i add-in startują,
- Word nie pokazuje błędu „Zawartość jest zablokowana...”,
- aktywne UI nie pokazuje już `v0.5`, `final2`, `final6`, `rc7`, `rc8`, `rc9`, `rc10`, `rc11`.

### 5. Test Word/WebView

W Wordzie:

1. Otwórz dokument testowy.
2. Uruchom dodatek CSM.
3. Sprawdź, czy panel ładuje się bez żółtej blokady.
4. Wykonaj pseudonimizację.
5. Wykonaj przywrócenie.
6. Jeżeli używasz śledzenia zmian, sprawdź, czy Word pokazuje zmiany jako rewizje.

DoD:

- Word ładuje panel CSM,
- brak komunikatu o zablokowanej zawartości,
- po pseudonimizacji dokument da się zapisać i otworzyć ponownie,
- mapa przywracania działa,
- przywrócenie odtwarza dane jawne tam, gdzie były pseudonimizowane,
- jeżeli mechanizm śledzenia zmian jest użyty, DOCX zawiera `w:ins` / `w:del` i Word pokazuje je jako śledzone zmiany.

### 6. Test pseudonimizacji prawniczej

Przetestuj co najmniej poniższe przypadki:

```text
Patryk Mucha
Renata Mucha
Anna Pustynia
Pustynia 84F, 39-200 Dębica
OLIMP LABORATORIES
Meble New Concept
na rzecz Pani Iwony Teresy Ustrzyckiej (PESEL: 90010112345)
Powód okazał dowód osobisty ABA300000.
Faktura VAT z dnia 18.12.2024 r. numer: 1234567890
Zlecenie numer 1469375
```

DoD:

- osoby są osobami, nawet jeśli nazwisko jest słowem pospolitym,
- miejscowość/adres są maskowane w kontekście adresowym,
- firma bez `sp. z o.o.` jest maskowana w kontekście strony/klienta/powoda/pozwanego,
- `ABA300000` jest `[IDCARD_PL_1]`, nie `[COMPANY_1]`,
- numer faktury nie jest `[NIP_1]`,
- `tekst jawny -> pseudonimizacja -> restore` daje tekst jawny albo uzasadnioną różnicę opisaną w raporcie.

### 7. Raport końcowy

Dołącz do paczki zwrotnej plik:

```text
CLAUDE_CODE_RC12_WINDOWS_FINALIZATION_REPORT.md
```

Raport musi zawierać:

- wersję Windows, Worda, Pythona, Node, npm, .NET SDK, Inno Setup,
- SHA-256 EXE,
- SHA-256 ZIP,
- pełne wyniki testów,
- informację, czy test Word/WebView był wykonany interaktywnie,
- informację, czy upgrade/repair z 0.5/final2/final6 był wykonany na realnym stanie,
- listę rzeczy niepotwierdzonych.

## Blokery finalnego 0.6.1

Nie oznaczaj jako finalne `0.6.1`, jeśli którekolwiek z poniższych jest niepotwierdzone:

- GUI installer bez zawieszenia,
- upgrade/repair po 0.5/final2/final6,
- certyfikat localhost `trusted=True`,
- Word/WebView bez blokady dodatku,
- realny sidecar przez skompilowany EXE,
- odwracalna pseudonimizacja na dokumentach prawniczych.

## Co jest poza zakresem 0.6 i należy zostawić na 0.7

- nowy silnik NLP/NER klasy Presidio albo spaCy,
- model scoringu ryzyka anonimizacji,
- centralny instalator firmowy/MSIX/GPO,
- podpis kodu EV/OV i reputacja SmartScreen,
- panel administracyjny,
- automatyczne uczenie się słownika kancelarii.
