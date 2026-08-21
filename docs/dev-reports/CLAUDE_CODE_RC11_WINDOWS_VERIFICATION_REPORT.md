# CLAUDE CODE RC11 — Windows Verification Report

**Data:** 2026-05-18  
**Wersja:** CSM v0.6.1-rc11-install-reversibility-security-wheelhouse-20260518  
**Środowisko:** Windows 11 Home 10.0.26200, Python 3.12.10, Node v24.15.0, .NET SDK 8.0.421, Inno Setup 6  

---

## SHA-256

| Artefakt | SHA-256 |
|---|---|
| Paczka wejściowa (źródło) | N/A — brak pliku ZIP; źródłem był folder `C:\Users\pkant\Desktop\CSM` |
| `CSM-Setup-v0.6.1.exe` | `23b941f1f436398cbe3e5330cafc8e1a45e263006b8ec64636e2002f3b4cdd87` |
| Paczka zwrotna | obliczana po spakowaniu |

---

## Prerekvizyta

| Komponent | Wersja | Status |
|---|---|---|
| Python | 3.12.10 | OK |
| Node | v24.15.0 | OK |
| npm | 11.12.1 | OK |
| .NET SDK | 8.0.421 | OK |
| Inno Setup | 6 | OK |

---

## Wheelhouse (server\wheelhouse)

Pobrane koła przez: `py -3.12 -m pip download --only-binary=:all: --platform win_amd64 --python-version 3.12`

| Paczka | Wersja | Plik |
|---|---|---|
| pip | 26.1.1 | pip-26.1.1-py3-none-any.whl |
| setuptools | 82.0.1 | setuptools-82.0.1-py3-none-any.whl |
| wheel | 0.47.0 | wheel-0.47.0-py3-none-any.whl |
| fastapi | 0.115.6 | fastapi-0.115.6-py3-none-any.whl |
| uvicorn | 0.34.0 | uvicorn-0.34.0-py3-none-any.whl |
| pydantic | 2.10.4 | pydantic-2.10.4-py3-none-any.whl |
| pydantic-core | 2.27.2 | pydantic_core-2.27.2-cp312-cp312-win_amd64.whl |
| python-dotenv | 1.0.1 | python_dotenv-1.0.1-py3-none-any.whl |
| lxml | 5.3.0 | lxml-5.3.0-cp312-cp312-win_amd64.whl |
| starlette | 0.41.3 | starlette-0.41.3-py3-none-any.whl |
| click | 8.4.0 | click-8.4.0-py3-none-any.whl |
| h11 | 0.16.0 | h11-0.16.0-py3-none-any.whl |
| anyio | 4.13.0 | anyio-4.13.0-py3-none-any.whl |
| idna | 3.15 | idna-3.15-py3-none-any.whl |
| annotated-types | 0.7.0 | annotated_types-0.7.0-py3-none-any.whl |
| typing-extensions | 4.15.0 | typing_extensions-4.15.0-py3-none-any.whl |
| colorama | 0.4.6 | colorama-0.4.6-py2.py3-none-any.whl |
| packaging | 26.2 | packaging-26.2-py3-none-any.whl |

**Łącznie: 18 plików .whl** — wszystkie wymagane paczki z `requirements-runtime.txt` i zależnościami obecne.

---

## Testy kodu przed buildem

### Lint i build JS

```
npm run lint --silent   → CSM lint validation passed for v0.6.1.   PASS
npm run build --silent  → CSM build validation passed for v0.6.1.  PASS
node --check addin/revision_bridge.js                               PASS
node --check addin/taskpane.js                                      PASS
node --check addin/scripts/validate-static.js                       PASS
```

### Python compileall

```
py -3.12 -m compileall -q server tests tools  → OK (zero errors)   PASS
```

### Pytest — grupa 1 (rc11 + install + hygiene)

```
tests/test_rc11_install_privacy_hardening.py
tests/test_idcard_passport_checksum.py
tests/test_installer_resilience_matrix.py
tests/test_installer_runtime_resilience_rc7.py
tests/test_release_hygiene.py
tests/test_final_assets_cache_and_mapping_ux.py

Wynik: 42 passed in 1.76s   PASS
```

### Pytest — grupa 2 (persons/context/workflow/restore)

```
tests/test_contextual_persons_and_roles.py
tests/test_identity_document_person_company_context.py
tests/test_pleadings_identifier_regression.py
tests/test_legal_lexicon_contracts_pleadings.py
tests/test_pseudonymization_extended_recommendations.py
tests/test_current_workflow.py
tests/test_restore_state_contract.py

Wynik: 27 passed in 2.27s   PASS
```

---

## Build .NET sidecar

```
dotnet restore  CSM.RevisionSidecar.csproj   → Przywrócono (675 ms)    OK
dotnet build    CSM.RevisionSidecar.csproj   → Kompilacja powiodła się  OK
TargetFramework: net8.0
Ostrzeżenia: 1 (CS8321 — nieużywana lokalna funkcja Sha256Hex)
Błędy: 0

dotnet test CSM.RevisionSidecar.Tests.csproj -c Release
→ Powodzenie! niepowodzenie: 0, powodzenie: 11, pominięto: 0   PASS
```

### Test Python → realny sidecar

```
CSM_REVISION_SIDECAR_CMD='.../CSM.RevisionSidecar.exe'
py -3.12 -m pytest -q tests/test_revision_sidecar_integration.py
→ 8 passed in 4.55s   PASS

Uwaga: przy użyciu 'dotnet run' (zamiast gotowego EXE) 3 testy failed z błędem 503
("Mechanizm zachowania śledzenia zmian nie jest podłączony") z powodu wolnego startu
procesu dotnet run. Przy wywołaniu przez zbudowany EXE: 8/8 PASS.
```

---

## Build EXE instalatora

```
ISCC.exe installer/CSM-Setup.iss
→ Successful compile (11,047 sec)
→ C:\Users\pkant\Desktop\CSM\installer\output\CSM-Setup-v0.6.1.exe

Rozmiar: 19 MB
SHA-256: 23b941f1f436398cbe3e5330cafc8e1a45e263006b8ec64636e2002f3b4cdd87
LicenseFile: LICENSE.txt — dołączony
Build tag: v0.6.1-rc11-install-reversibility-security-wheelhouse-20260518   PASS
```

---

## Clean install / Upgrade po 0.5

### Scenariusz: upgrade z rc4/rc8 era (C:\CSM zawierało starą wersję)

```
CSM-Setup-v0.6.1.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
→ exit code: 0
→ Installation process succeeded.
→ install-csm.ps1 uruchomiony automatycznie po rozpakowaniu plików    PASS
```

### Weryfikacja po instalacji

| Test | Wynik |
|---|---|
| `C:\CSM\server\.venv\Scripts\python.exe` istnieje | PASS |
| `import fastapi, uvicorn, pydantic, lxml.etree` w .venv | PASS |
| `VERSION.json` build = `v0.6.1-rc11-install-reversibility-security-wheelhouse-20260518` | PASS |
| Backend `/health` zwraca `version: 0.6.1` | PASS |
| HTTPS serwer add-in `https://localhost:3000/taskpane.html` odpowiada | PASS |
| Certyfikat localhost w `CurrentUser\Root` (CN=localhost, NotAfter: 2036) | PASS |
| Panel pokazuje `v0.6.1 — rc11` | PASS |
| JS cache-busters zawierają `rc11` (`?v=0.6.1-rc11-20260518`) | PASS |

### Wheelhouse offline

Koła w `server\wheelhouse` dołączone do EXE — instalacja nie wymaga PyPI.  
Weryfikacja: `setup-once.ps1` obsługuje `--no-index --find-links` gdy `server\wheelhouse` zawiera `.whl` — **PASS** (potwierdzony przez test `test_installer_resilience_matrix.py`).

---

## Test odwracalnej pseudonimizacji

### Poprawka ABA300000

```python
make_replacements('Powód okazał dowód osobisty ABA300000.')
→ 'Powód okazał dowód osobisty [IDCARD_PL_1].'
[IDCARD_PL_1] in output: True
[COMPANY_1] not in output: True   PASS
```

### Backup DPAPI

```
tests/test_rc11_install_privacy_hardening.py: 3 passed   PASS

Potwierdzono:
- backup_payload.csmmap tworzony zamiast original_document.docx / original_visible_text.txt
- load_install_backup() odczytuje chroniony payload
- na Windows: protection_method = windows-dpapi-current-user
```

---

## Rzeczy niepotwierdzono w tym przebiegu

| Element | Powód |
|---|---|
| Word bez blokady żółtego paska | Wymaga interaktywnego testu w Word z załadowanym add-in |
| Word tracked changes (w:ins/w:del) | Wymaga sesji Word z dokumentem DOCX |
| Pełna pseudonimizacja w Word na dokumentach prawniczych | Wymaga interaktywnego Word |
| Test upgrade z CSM 0.5 / final2 / final6 | Na maszynie testowej był rc4/rc8 era, nie 0.5 |
| Zawieszenie paska instalatora | Nie można obserwować w silent install |

---

## Podsumowanie DoD

| DoD | Status |
|---|---|
| EXE istnieje po wypełnieniu wheelhouse | **PASS** |
| EXE zawiera LicenseFile | **PASS** |
| EXE zawiera rc11, nie rc10/rc9/rc8/rc7 | **PASS** |
| Zero failed testów pre-build | **PASS** |
| .NET sidecar net8.0, zero failed | **PASS** |
| Sidecar integration 8/8 passed | **PASS** |
| C:\CSM\server\.venv\Scripts\python.exe istnieje | **PASS** |
| fastapi, uvicorn, pydantic, lxml importują się w .venv | **PASS** |
| Backend działa na 127.0.0.1:8787 | **PASS** |
| HTTPS add-in działa na https://localhost:3000 | **PASS** |
| Certyfikat localhost trusted | **PASS** |
| Panel pokazuje v0.6.1 — rc11 | **PASS** |
| ABA300000 → [IDCARD_PL_1], nie [COMPANY_1] | **PASS** |
| backup_payload.csmmap bez jawnych plików oryginału | **PASS** |
| Word — interaktywny test | **NIEPOTWIERDZONE** |
| Upgrade z 0.5/final2/final6 | **NIEPOTWIERDZONE** |
