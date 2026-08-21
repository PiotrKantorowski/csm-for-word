@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start-claude-safe-mode.ps1" -NoOpenWord -NonInteractive
pause
