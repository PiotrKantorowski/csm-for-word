# CLAUDE_CODE_RC13_FINALIZATION_REPORT

Generated: 2026-05-18  
Build candidate: `CSM v0.6.1 rc13`

---

## 1. Wejście — SHA-256 źródłowego ZIP

| Plik | SHA-256 |
|------|---------|
| `CSM_v0_6_1_rc13_polish_pseudonymization_install_SOURCE.zip` | `dfba79239bfd8182f7f9ca720badcb0dcdb8495d41a400964cc6e22a5ab1cd80` |

---

## 2. SHA-256 zbudowanego EXE

| Plik | SHA-256 | Rozmiar |
|------|---------|---------|
| `installer/output/CSM-Setup-v0.6.1.exe` | `ac174ac154a7a565ac21e1200de6382e3f827300d0e127f63bfb4cfa48cdadc3` | 19 MB |

---

## 3. Wersje narzędzi

| Narzędzie | Wersja |
|-----------|--------|
| Python | 3.12.10 |
| Node.js | 24.15.0 |
| npm | 11.12.1 |
| .NET SDK | 8.0.421 |
| Inno Setup | 6.7.1 |

---

## 4. Walidacja źródła

### Wyniki — WSZYSTKIE PASS

| Komenda | Wynik |
|---------|-------|
| `npm run lint --silent` | PASS |
| `npm run build --silent` | PASS |
| `node --check addin/revision_bridge.js` | PASS |
| `node --check addin/taskpane.js` | PASS |
| `node --check addin/scripts/validate-static.js` | PASS |
| `py -3.12 -m compileall -q server tests tools` | PASS |

### Poprawka pytest.ini

Dodano `pythonpath = server` do `pytest.ini`, co naprawia `ModuleNotFoundError: No module named 'redactor'` przy uruchamianiu testów z katalogu głównego.

---

## 5. Python pytest — wyniki

### Testy główne (51 passed)

```
tests/test_rc13_polish_pseudonymization_rules.py         4 passed
tests/test_pseudonymization_extended_recommendations.py  (included in 51)
tests/test_legal_lexicon_contracts_pleadings.py          (included in 51)
tests/test_rc11_install_privacy_hardening.py             (included in 51)
tests/test_installer_resilience_matrix.py                (included in 51)
tests/test_release_hygiene.py                            (included in 51)
tests/test_final_assets_cache_and_mapping_ux.py          (included in 51)
tests/test_installer_runtime_resilience_rc7.py           (included in 51)

ŁĄCZNIE: 51 passed, 0 failed
```

### Testy sidecar/frontend (bez skompilowanego EXE)

```
tests/test_revision_sidecar_integration.py   (8 passed + 3 skipped przed buildem)
tests/test_revision_sidecar_contract.py      (included)
tests/test_revision_sidecar_frontend_sync.py (included)

ŁĄCZNIE: 19 passed, 3 skipped (oczekiwane — brak CSM_REVISION_SIDECAR_CMD przed buildem)
```

---

## 6. .NET sidecar — dotnet restore / build / test

```
dotnet restore CSM.RevisionSidecar.csproj        → OK (933 ms)
dotnet build   CSM.RevisionSidecar.csproj -c Release --no-restore
  → Kompilacja powiodła się. Ostrzeżenia: 1 (CS8321 unused local fn), Błędy: 0
dotnet restore CSM.RevisionSidecar.Tests.csproj  → OK
dotnet test    CSM.RevisionSidecar.Tests.csproj -c Release --no-restore
  → Powodzenie! niepowodzenie: 0, powodzenie: 11, pominięto: 0
```

---

## 7. Sidecar integration przez skompilowany EXE

```
CSM_REVISION_SIDECAR_CMD = sidecar/CSM.RevisionSidecar/bin/Release/net8.0/CSM.RevisionSidecar.exe
py -3.12 -m pytest -q tests/test_revision_sidecar_integration.py

WYNIK: 8 passed — 100% PASS
```

---

## 8. Wheelhouse — weryfikacja offline pip

Katalog `server/wheelhouse` zawiera 18 kół dla Python 3.12 / Windows x64:

```
annotated_types-0.7.0, anyio-4.13.0, click-8.4.0, colorama-0.4.6,
fastapi-0.115.6, h11-0.16.0, idna-3.15, lxml-5.3.0 (cp312-win_amd64),
packaging-26.2, pip-26.1.1, pydantic-2.10.4, pydantic_core-2.27.2 (cp312-win_amd64),
python_dotenv-1.0.1, setuptools-82.0.1, starlette-0.41.3,
typing_extensions-4.15.0, uvicorn-0.34.0, wheel-0.47.0
```

Status: kompletny wheelhouse dla instalacji offline (--no-index --find-links).

---

## 9. Build instalatora EXE

```
ISCC.exe installer/CSM-Setup.iss
→ Successful compile (15,734 sec)
→ CSM-Setup-v0.6.1.exe — 19 MB

Weryfikacja tagów:
- addin/taskpane.html: <div class="build-badge">v0.6.1 — rc13</div>   ✓
- addin/taskpane.html: ?v=0.6.1-rc13-20260518                         ✓
- VERSION.json: "build": "v0.6.1-rc13-polish-pseudonymization-install-hygiene-20260518"  ✓
- tools/install-csm.ps1: "CSM v0.6.1 rc13 - instalacja jednym plikiem"  ✓
- Brak etykiet rc11/rc12 w plikach źródłowych                         ✓
- LicenseFile obecny w CSM-Setup.iss                                   ✓
```

---

## 10. Pseudonimizacja polska — test RC13 rulebook

Wszystkie 4 nowe reguły z `CSM_POLISH_PSEUDONYMIZATION_RULEBOOK_RC13.md` przeszły testy:

| Test | Reguła | Wynik |
|------|--------|-------|
| `test_party_label_person_is_person_not_company` | `Powód Jan Nowak` → `PERSON`, nie `COMPANY` | PASS |
| `test_residence_locality_without_street_is_masked_in_address_context` | `zamieszkały w Pustyni` → `ADDRESS` | PASS |
| `test_bank_account_after_owner_name_is_masked_even_if_fixture_number_is_fictional` | `Rachunek bankowy Jana Nowaka: PL ...` → maskowany nawet dla fikcyjnych numerów | PASS |
| `test_company_context_still_masks_uppercase_party_company` | `Powód: OLIMP LABORATORIES` → `COMPANY` | PASS |

---

## 11. GUI install — test ręczny

**Status: NIEPOTWIERDZONY** — wymaga ręcznego uruchomienia `CSM-Setup-v0.6.1.exe` bez `/VERYSILENT`.

Punkty do weryfikacji:
- [ ] Ekran licencji blokuje przejście bez akceptacji
- [ ] Koniec instalacji bez zawieszenia paska postępu
- [ ] `%TEMP%\CSM-install.log` bez błędów pip cache
- [ ] `%TEMP%\CSM-setup-once.log` — brak błędów
- [ ] `C:\CSM\server\.venv\Scripts\python.exe` istnieje
- [ ] `https://localhost:3000/taskpane.html` odpowiada
- [ ] `http://127.0.0.1:8787/health` odpowiada

---

## 12. Upgrade/repair po CSM 0.5/final2/final6

**Status: NIEPOTWIERDZONY** — wymaga maszyny ze starą instalacją.

Punkty do weryfikacji:
- [ ] Stare cache Worda są czyszczone
- [ ] Uszkodzone `.venv` jest wykryte i odbudowane
- [ ] Stary certyfikat/brak certyfikatu jest naprawiony
- [ ] Panel pokazuje rc13, nie 0.5/final
- [ ] `/health` zwraca `version: 0.6.1`
- [ ] Certyfikat `localhost` ma `trusted=True`
- [ ] Brak etykiet `final2/final6` w cache-busterach

---

## 13. Word / WebView

**Status: NIEPOTWIERDZONY** — wymaga Microsoft Word z dodatkiem.

Punkty do weryfikacji:
- [ ] Brak komunikatu o zablokowanym dodatku
- [ ] Panel i status techniczny ładują się poprawnie
- [ ] Pseudonimizacja na realnym DOCX (pozew, umowa, akt notarialny)
- [ ] Restore przywraca dokument do oryginału
- [ ] Śledzenie zmian z sidecarem (jeśli dostępny)

---

## 14. Podsumowanie — co potwierdzone automatycznie

| Obszar | Status |
|--------|--------|
| Lint / Build / Node check / compileall | ✅ PASS |
| pytest (51 testów) | ✅ 51 passed |
| pytest sidecar (pre-build) | ✅ 19 passed, 3 skipped (oczekiwane) |
| dotnet build sidecar | ✅ 0 błędów |
| dotnet test sidecar (11 testów) | ✅ 11 passed |
| Sidecar integration przez EXE (8 testów) | ✅ 8 passed |
| Wheelhouse (18 kół) | ✅ kompletny |
| EXE build (Inno Setup 6.7.1) | ✅ zbudowany, 19 MB |
| Etykiety rc13 w EXE | ✅ bez rc11/rc12 |
| RC13 pseudonimizacja polska (4 reguły) | ✅ 4 passed |
| GUI installer | ⬜ wymaga ręcznego testu |
| Upgrade/repair po 0.5 | ⬜ wymaga ręcznego testu |
| Word / WebView | ⬜ wymaga ręcznego testu |

---

## 15. Nazwa paczki zwrotnej

Ponieważ GUI, upgrade/repair i Word/WebView nie są potwierdzone ręcznie:

```
CSM_v0_6_1_rc13_WINDOWS_TESTED_WITH_FAILURES.zip
```

Nie używać nazwy `FINAL` ani `WINDOWS_VERIFIED` do czasu ręcznego potwierdzenia wszystkich blokerów.
