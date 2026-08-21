# CSM-Setup.exe

Ten katalog zawiera pierwszy, produkcyjny szkielet budowy jednoplikowego instalatora CSM.

## Założenie

Docelowy artefakt:

```text
CSM-Setup-v1.0.exe
```

Instalator kopiuje CSM do `C:\CSM`, uruchamia istniejący skrypt `tools/install-csm.ps1`, konfiguruje lokalny katalog dodatku Word, autostart, skróty oraz deinstalator. To jest etap przejściowy zgodny z obecną architekturą ZIP + PowerShell, ale bez ręcznego rozpakowywania przez użytkownika.

## Budowa lokalna na Windows

1. Zainstaluj Inno Setup 6.
2. Uruchom PowerShell w katalogu repozytorium.
3. Wykonaj:

```powershell
.\installer\build-csm-setup.ps1
```

Wynik pojawi się w:

```text
installer\output\CSM-Setup-v1.0.exe
```

## Kolejny etap

W v0.8.x warto dodać zamrożenie backendu do `csm-backend.exe` i `csm-addin-server.exe` przez PyInstaller/Nuitka, aby użytkownik końcowy nie potrzebował lokalnego środowiska Python.

## Licencja

Instalator musi pokazać użytkownikowi ekran licencji i wymagać jej akceptacji przed rozpoczęciem instalacji. W skrypcie Inno Setup odpowiada za to `LicenseFile={#SourceDir}\LICENSE.txt`.

Nie publikuj `installer\output\CSM-Setup-v1.0.exe`, jeżeli został zbudowany przed dodaniem `LicenseFile`, bo taki plik nie pokazuje obowiązkowego ekranu akceptacji licencji.
