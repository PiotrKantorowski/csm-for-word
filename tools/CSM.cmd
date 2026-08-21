@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PANEL=%SCRIPT_DIR%CSM.ps1"
if not exist "%PANEL%" (
  echo [CSM] Nie znaleziono panelu: %PANEL%
  echo Upewnij sie, ze uruchamiasz CSM z kompletnego katalogu instalacji.
  echo Jesli cos nie dziala, napisz na csm@kancelariakantorowski.pl - pomoze nam to rozwiazac Twoj problem.
  pause
  exit /b 1
)
powershell -NoProfile -STA -ExecutionPolicy Bypass -File "%PANEL%"
if errorlevel 1 (
  echo.
  echo [CSM] Panel zakonczyl sie bledem. Sprobuj uruchomic NAPRAW albo zainstaluj CSM ponownie.
  echo Jesli cos nie dziala, napisz na csm@kancelariakantorowski.pl - pomoze nam to rozwiazac Twoj problem.
  pause
  exit /b 1
)
