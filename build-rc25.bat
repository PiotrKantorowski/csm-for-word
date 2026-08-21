@echo off
echo Building RC25...

REM Copy installer to Desktop
copy /Y "C:\Users\pkant\Desktop\CSM-rc17-src\installer\output\CSM-Setup-v0.6.1.exe" "C:\Users\pkant\Desktop\CSM-Setup-v0.6.1-rc25.exe"
echo Installer copy exit: %errorlevel%

REM Build ZIP
powershell -NoProfile -Command "Compress-Archive -Path 'C:\Users\pkant\Desktop\CSM-rc17-src' -DestinationPath 'C:\Users\pkant\Desktop\CSM_v0.6.1_rc25_src.zip' -Force; Write-Host 'ZIP done'"

echo Done.
