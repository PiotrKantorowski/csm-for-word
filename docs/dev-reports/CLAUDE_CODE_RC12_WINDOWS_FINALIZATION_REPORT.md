# CLAUDE CODE RC12 — Windows Finalization Report

**Data:** 2026-05-18  
**Wersja:** CSM v0.6.1-rc12-ci-sidecar-exe-20260518  
**Środowisko:** Windows 11 Home 10.0.26200, Python 3.12.10, Node v24.15.0 / npm 11.12.1, .NET SDK 8.0.421, Inno Setup 6

---

## SHA-256

| Artefakt | SHA-256 |
|---|---|
| `CSM_v0_6_1_rc12_ci_sidecar_exe_SOURCE.zip` | `d1acde4047214c59f8f0fe4a2a0dff6a467482b0bfbd9b2065e5e2bae7c4d6a7` |
| `CSM-Setup-v0.6.1.exe` | `55c020ca4f13318c50816a5fe1766800fca7151ca12e150a627e84e4511c8b95` |
| Paczka zwrotna | obliczana poniżej |

---

## Zmiany rc12 względem rc11

- GitHub Actions CI (`.github/workflows/build-csm-installer.yml`) używa teraz skompilowanego `CSM.RevisionSidecar.exe` zamiast `dotnet run` do testu integracyjnego — eliminuje fałszywe błędy 503 przy wolnym starcie `dotnet run`.
- Zaktualizowane labelki: `build-badge`, cache-bustery JS, manifest.xml → `rc12`.
- `engine_version` w `redactor.py`: `0.2.41-rc12-ci-sidecar-exe`.
- Testy `test_final_assets_cache_and_mapping_ux.py` i `test_installer_runtime_resilience_rc7.py` zaktualizowane do nowych label rc12.

---

## Prerekvizyta

| Komponent | Wersja |
|---|---|
| Python | 3.12.10 |
| Node | v24.15.0 |
| npm | 11.12.1 |
| .NET SDK | 8.0.421 |
| Inno Setup | 6 |

---

## Wheelhouse (server\wheelhouse)

18 plików `.whl` dla Python 3.12 / Windows x64 — bez zmian względem rc11:

```
fastapi-0.115.6, uvicorn-0.34.0, pydantic-2.10.4, pydantic_core-2.27.2 (win_amd64),
python_dotenv-1.0.1, lxml-5.3.0 (cp312-win_amd64), starlette-0.41.3, click-8.4.0,
h11-0.16.0, anyio-4.13.0, idna-3.15, annotated_types-0.7.0, typing_extensions-4.15.0,
colorama-0.4.6, packaging-26.2, pip-26.1.1, setuptools-82.0.1, wheel-0.47.0
```

---

## Testy kodu przed buildem

```
npm run lint --silent    → CSM lint validation passed for v0.6.1.   PASS
npm run build --silent   → CSM build validation passed for v0.6.1.  PASS
node --check revision_bridge.js / taskpane.js / validate-static.js  PASS
py -3.12 -m compileall -q server tests tools                         PASS
```

### Pytest — wszystkie grupy

```
tests/test_rc11_install_privacy_hardening.py
tests/test_idcard_passport_checksum.py
tests/test_installer_resilience_matrix.py
tests/test_installer_runtime_resilience_rc7.py
tests/test_release_hygiene.py
tests/test_final_assets_cache_and_mapping_ux.py
tests/test_contextual_persons_and_roles.py
tests/test_identity_document_person_company_context.py
tests/test_pleadings_identifier_regression.py
tests/test_legal_lexicon_contracts_pleadings.py
tests/test_pseudonymization_extended_recommendations.py
tests/test_current_workflow.py
tests/test_restore_state_contract.py

Wynik: 69 passed in 4.62s — ZERO FAILED   PASS
```

*Uwaga: Przed finalnym przebiegiem 3 testy failed po aktualizacji labelek rc11→rc12. Naprawiono hardcodowane oczekiwania w testach + usunięto foldery `bin/obj` (test `test_release_hygiene` zakazuje ich w źródle). Po naprawie: 69/69.*

---

## Build .NET sidecar

```
dotnet restore  CSM.RevisionSidecar.csproj  → OK (850 ms)
dotnet build    CSM.RevisionSidecar.csproj  -c Release --no-restore → OK
TargetFramework: net8.0
Błędy: 0, Ostrzeżenia: 1 (CS8321 — nieużywana funkcja Sha256Hex)

dotnet restore  CSM.RevisionSidecar.Tests.csproj → OK
dotnet test     CSM.RevisionSidecar.Tests.csproj -c Release --no-restore
→ Powodzenie! niepowodzenie: 0, powodzenie: 11, pominięto: 0   PASS
```

### Test Python → realny sidecar EXE

```
CSM_REVISION_SIDECAR_CMD = CSM-rc12/sidecar/.../net8.0/CSM.RevisionSidecar.exe

py -3.12 -m pytest -q tests/test_revision_sidecar_integration.py
→ 8 passed in 4.95s   PASS

Użyto skompilowanego EXE (nie dotnet run) — zgodnie z poprawką rc12.
```

---

## Build EXE instalatora

```
ISCC.exe installer/CSM-Setup.iss
→ Successful compile (12,547 sec)
→ CSM-rc12/installer/output/CSM-Setup-v0.6.1.exe

Rozmiar: 15 MB
SHA-256: 55c020ca4f13318c50816a5fe1766800fca7151ca12e150a627e84e4511c8b95
LicenseFile: LICENSE.txt — dołączony
Build tag: v0.6.1-rc12-ci-sidecar-exe-20260518   PASS
```

---

## Test pseudonimizacji prawniczej (kod)

| Przypadek testowy | Wynik | Status |
|---|---|---|
| `Jan Mucha` (bez kontekstu) | `[PERSON_1]` | PASS |
| `Renata Mucha` | `[PERSON_1]` | PASS |
| `Anna Pustynia` | `[PERSON_1]` | PASS |
| `Pustynia 84F, 39-200 Debica` | `[ADDRESS_RURAL_1]` | PASS |
| `Powod: OLIMP LABORATORIES, ul. Testowa 1...` | `[COMPANY_1], [ADDRESS_FULL_1]` | PASS |
| `Pozwany: Meble New Concept sp. z o.o.` | `[COMPANY_1]` | PASS |
| `Klient: Meble New Concept` | `[COMPANY_1]` | PASS |
| `OLIMP LABORATORIES` (izolacja) | SAME — brak kontekstu | OCZEKIWANE¹ |
| `Pani Iwona Teresa Ustrzycka (PESEL: 90010112345)` | `[PERSON_1] [PERSON_2_ALIAS_1] (PESEL: [PESEL_1])` | PASS |
| `Powod okazal dowod osobisty ABA300000.` | `[IDCARD_PL_1]` (nie COMPANY) | PASS |
| `Faktura VAT z dnia 18.12.2024 r. numer: 1234567890` | `[FINANCIAL_DOC_ID_1]` (nie NIP) | PASS |
| `Zlecenie numer 1469375` | `[PROJECT_ID_1]` | PASS |

¹ Firma bez kontekstu prawniczego (Powód/Pozwany/Klient) nie jest maskowana z definicji — zgodnie z DoD.

### Roundtrip (pseudonimizacja → restore → oryginalny tekst)

```
[PASS] 'Jan Mucha reprezentuje Klienta: OLIMP LABORATORIES'
[PASS] 'Powod okazal dowod osobisty ABA300000'
[PASS] 'Pustynia 84F, 39-200 Debica'
[PASS] 'Pani Iwona Teresa Ustrzycka (PESEL: 90010112345)'
[PASS] 'Faktura VAT numer: 1234567890'

ROUNDTRIP: ALL PASS
```

---

## Test GUI instalatora

**NIEPOTWIERDZONE automatycznie** — wymaga interaktywnego testu przez użytkownika.

Zalecane kroki:
1. Uruchom `installer\output\CSM-Setup-v0.6.1.exe` normalnie (bez /VERYSILENT).
2. Sprawdź ekran licencji — bez akceptacji nie można kontynuować.
3. Sprawdź, że instalator nie zawiesza się na końcu paska.
4. Po instalacji sprawdź `%TEMP%\CSM-install.log` i `%TEMP%\CSM-setup-once.log`.

---

## Test upgrade/repair z CSM 0.5 / final2 / final6

**NIEPOTWIERDZONE** — wymaga realnej instalacji starego CSM 0.5/final2/final6.

W rc11 wykonano upgrade z rc4/rc8 era (silent install, exit 0, PASS). Upgrade z prawdziwego 0.5/final2/final6 nie był dostępny na tej maszynie testowej.

---

## Test Word/WebView

**NIEPOTWIERDZONE automatycznie** — wymaga interaktywnego testu w Microsoft Word.

Potwierdzone pośrednio:
- Certyfikat localhost w `CurrentUser\Root` (NotAfter: 2036) — PASS w rc11
- HTTPS serwer add-in `https://localhost:3000/taskpane.html` odpowiada — PASS w rc11
- Panel HTML zawiera `v0.6.1 — rc12` — PASS

---

## Blokery finalnego 0.6.1 — status

| Bloker | Status |
|---|---|
| GUI installer bez zawieszenia | **NIEPOTWIERDZONE** — wymaga testu ręcznego |
| Upgrade/repair po 0.5/final2/final6 | **NIEPOTWIERDZONE** — wymaga realnego stanu 0.5 |
| Certyfikat localhost trusted=True | **PASS** (rc11, RC12 bez zmian) |
| Word/WebView bez blokady | **NIEPOTWIERDZONE** — wymaga testu ręcznego |
| Realny sidecar przez skompilowany EXE | **PASS** (8/8 testów integracyjnych) |
| Odwracalna pseudonimizacja — roundtrip | **PASS** (kod + 69 testów pytest) |

---

## Podsumowanie DoD

| DoD | Status |
|---|---|
| `dotnet build` — 0 błędów | **PASS** |
| `dotnet test` — 0 failed, 0 skipped | **PASS** |
| Sidecar integration 8/8 przez EXE | **PASS** |
| Pytest 69/69 — zero failed | **PASS** |
| EXE istnieje z wheelhouse | **PASS** |
| EXE zawiera rc12 (nie rc11/rc10) | **PASS** |
| Roundtrip pseudonimizacji | **PASS** |
| ABA300000 → [IDCARD_PL_1] | **PASS** |
| Faktura numer → [FINANCIAL_DOC_ID_1] (nie NIP) | **PASS** |
| GUI installer — obserwacja ręczna | **WYMAGANE OD UŻYTKOWNIKA** |
| Upgrade z 0.5/final2/final6 | **WYMAGANE OD UŻYTKOWNIKA** |
| Word/WebView bez blokady | **WYMAGANE OD UŻYTKOWNIKA** |
