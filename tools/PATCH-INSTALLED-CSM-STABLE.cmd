@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0PATCH-INSTALLED-CSM-STABLE.ps1" %*
