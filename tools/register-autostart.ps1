param([string]$InstallDir = "C:\CSM")
$ErrorActionPreference = "Stop"
$TaskName = "CSM AutoStart"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$StartScript = Join-Path $InstallDir "tools\start-claude-safe-mode.ps1"
if (-not (Test-Path -LiteralPath $StartScript)) { throw "Nie znaleziono skryptu startowego CSM: $StartScript" }

$psArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$StartScript`" -NoOpenWord -NonInteractive"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs -WorkingDirectory $InstallDir
try { $trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId }
catch { $trigger = New-ScheduledTaskTrigger -AtLogOn }

$settingsCommand = Get-Command New-ScheduledTaskSettingsSet -ErrorAction Stop
$settingsParams = @{ StartWhenAvailable = $true; MultipleInstances = "IgnoreNew" }
if ($settingsCommand.Parameters.ContainsKey("AllowStartIfOnBatteries")) { $settingsParams["AllowStartIfOnBatteries"] = $true }
if ($settingsCommand.Parameters.ContainsKey("DisallowStartIfOnBatteries")) { $settingsParams["DisallowStartIfOnBatteries"] = $false }
$settings = New-ScheduledTaskSettingsSet @settingsParams

$principal = $null
try {
    $principal = New-ScheduledTaskPrincipal -UserId $UserId -LogonType Interactive -RunLevel Limited
} catch {
    Write-Host "Ostrzezenie: nie udalo sie utworzyc Principal z RunLevel Limited. Uzywam prostszego zadania: $($_.Exception.Message)" -ForegroundColor Yellow
}

if ($principal) {
    $task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description "Uruchamia lokalne uslugi CSM po zalogowaniu uzytkownika, bez otwierania Worda."
} else {
    $task = New-ScheduledTask -Action $action -Trigger $trigger -Settings $settings -Description "Uruchamia lokalne uslugi CSM po zalogowaniu uzytkownika, bez otwierania Worda."
}

try {
    Register-ScheduledTask -TaskName $TaskName -InputObject $task -Force | Out-Null
} catch {
    Write-Host "Ostrzezenie: standardowa rejestracja zadania nie powiodla sie. Probuje bez Principal/User: $($_.Exception.Message)" -ForegroundColor Yellow
    $simpleTask = New-ScheduledTask -Action $action -Trigger (New-ScheduledTaskTrigger -AtLogOn) -Settings $settings -Description "Uruchamia lokalne uslugi CSM po zalogowaniu uzytkownika, bez otwierania Worda."
    Register-ScheduledTask -TaskName $TaskName -InputObject $simpleTask -Force | Out-Null
}
Write-Host "Wlaczono autostart CSM przy logowaniu uzytkownika: $TaskName ($UserId)" -ForegroundColor Green
