@echo off
setlocal
set SCRIPT_DIR=%~dp0
set INSTALLER=%SCRIPT_DIR%tools\install-csm.ps1
if not exist "%INSTALLER%" (
  echo [CSM] Nie znaleziono instalatora: %INSTALLER%
  echo Upewnij sie, ze paczka zostala rozpakowana w calosci.
  echo Jesli cos nie dziala, napisz na csm@kancelariakantorowski.pl - pomoze nam to rozwiazac Twoj problem.
  pause
  exit /b 1
)
where pwsh.exe >nul 2>&1 && set PSEXE=pwsh.exe || set PSEXE=PowerShell
%PSEXE% -NoProfile -ExecutionPolicy Bypass -File "%INSTALLER%" -AcceptLicense
if errorlevel 1 (
  echo.
  echo [CSM] Instalacja zakonczyla sie bledem.
  echo Jesli cos nie dziala, napisz na csm@kancelariakantorowski.pl - pomoze nam to rozwiazac Twoj problem.
  pause
  exit /b 1
)
exit /b 0
