# Creates one desktop shortcut for the CSM launcher panel.
param(
    [string]$InstallDir = "",
    [string]$DesktopPath = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ($InstallDir) { $InstallDir } elseif ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$ToolsDir = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { $ScriptDir } else { Join-Path $Root "tools" }
if ($InstallDir) { $ToolsDir = Join-Path $InstallDir "tools" }
$Desktop = if ($DesktopPath) { $DesktopPath } else { [Environment]::GetFolderPath("Desktop") }

if (-not (Test-Path -LiteralPath $Desktop)) {
    New-Item -ItemType Directory -Force -Path $Desktop | Out-Null
}

$Launcher = Join-Path $ToolsDir "CSM.ps1"

$IconPath = Join-Path $Root "assets\csm.ico"
if (-not (Test-Path -LiteralPath $IconPath)) { $IconPath = Join-Path $Root "addin\assets\csm.ico" }
if (-not (Test-Path -LiteralPath $Launcher)) {
    throw "Nie znaleziono panelu CSM: $Launcher"
}

$Shell = New-Object -ComObject WScript.Shell
function Remove-OldShortcut($Name) {
    $Path = Join-Path $Desktop "$Name.lnk"
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Force }
}
foreach ($name in @("CSM", "CSM - START", "CSM - STOP", "CSM - CLEAN", "CSM-CLEAN", "CSM-DIAGNOZA", "NAPRAW_CSM", "ODINSTALUJ_CSM")) { Remove-OldShortcut $name }

$ShortcutPath = Join-Path $Desktop "CSM.lnk"
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$Shortcut.Arguments = "-NoProfile -STA -ExecutionPolicy Bypass -File `"$Launcher`""
$Shortcut.WorkingDirectory = $Root
$Shortcut.Description = "Panel CSM: START, STOP, CLEAN, DIAGNOZA, NAPRAW, ODINSTALUJ"
if (Test-Path -LiteralPath $IconPath) { $Shortcut.IconLocation = $IconPath }
$Shortcut.Save()
Write-Host "Utworzono skrot: $ShortcutPath" -ForegroundColor Green
