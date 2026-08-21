# CSM v0.6.1-rc7 — odbudowanie instalatora EXE po poprawkach

Ta paczka zawiera poprawki w skryptach instalacyjnych i anonimizacji pism procesowych. Stary `installer/output/CSM-Setup-v0.6.1.exe` został usunięty, bo był zbudowany przed poprawkami rc7.

## Zakres dla Claude Code / Windows

1. Uruchomić na czystym Windowsie z Inno Setup:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File installer\build-csm-setup.ps1
```

2. Potwierdzić, że powstał:

```text
installer\output\CSM-Setup-v0.6.1.exe
```

3. Na maszynie testowej bez wcześniejszego CSM wykonać instalację z EXE i sprawdzić:

- instalator pokazuje licencję i wymaga akceptacji,
- instalacja nie kończy się błędem przez `WARNING: Cache entry deserialization failed`,
- `.venv` zawiera `fastapi` i `uvicorn`,
- `http://127.0.0.1:8787/health` zwraca 200,
- `https://localhost:3000/taskpane.html` otwiera się bez błędu certyfikatu,
- diagnostyka pokazuje `trusted=True`,
- Word nie pokazuje komunikatu „Zawartość jest zablokowana...”,
- anonimizacja pozwu nie klasyfikuje numeru faktury jako `[NIP_n]`.

## DoD

- `npm run lint --silent`: PASS
- `npm run build --silent`: PASS
- `python -m compileall -q server tests tools`: PASS
- `python -m pytest -q tests/test_pleadings_identifier_regression.py tests/test_installer_runtime_resilience_rc7.py tests/test_release_hygiene.py`: PASS
- EXE odbudowany po poprawkach rc7
- test instalacji EXE na świeżym profilu Windows przechodzi
- test Word/WebView przechodzi
