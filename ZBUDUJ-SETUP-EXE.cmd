@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo CSM for Word 1.5 - budowanie setup.exe
if not exist "installer\CSM-Setup.iss" (
  echo Nie znaleziono installer\CSM-Setup.iss. Uruchom ten plik z katalogu zrodlowego CSM.
  pause
  exit /b 2
)
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if "%ISCC%"=="" (
  echo Nie znaleziono Inno Setup 6/7 / ISCC.exe.
  echo Zainstaluj Inno Setup 6: https://jrsoftware.org/isdl.php
  pause
  exit /b 1
)
where python >nul 2>nul
if errorlevel 1 (
  echo Brak Python w PATH. Zainstaluj Python 3.11+ i sprobuj ponownie.
  pause
  exit /b 1
)
echo Uruchamiam testy przed budowa...
call npm run test
if errorlevel 1 (
  echo Testy nie przeszly. Nie buduje setup.exe.
  pause
  exit /b 1
)
if exist installer\output rmdir /s /q installer\output
mkdir installer\output
"%ISCC%" installer\CSM-Setup.iss
if errorlevel 1 (
  echo Budowanie setup.exe nie powiodlo sie.
  pause
  exit /b 1
)
if not exist "installer\output\CSM-Setup-v1.6.exe" (
  echo Nie znaleziono oczekiwanego pliku installer\output\CSM-Setup-v1.6.exe.
  pause
  exit /b 1
)
(
  echo Ten katalog zawiera pliki wyjsciowe instalatora CSM.
  echo.
  echo CSM-Setup-v1.6.exe - celowo nie ma go w repozytorium zrodlowym.
  echo Plik instalatora jest generowany lokalnie przez skrypt build-csm-setup.ps1
  echo i nie jest dolaczany do paczki zrodlowej.
  echo.
  echo Aby zbudowac instalator, uruchom:
  echo   .\installer\build-csm-setup.ps1
) > "installer\output\README-SETUP-NOT-INCLUDED.txt"
echo.
echo Gotowe: installer\output\CSM-Setup-v1.6.exe
pause
