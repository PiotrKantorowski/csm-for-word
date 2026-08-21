param(
    [string]$InstallDir = "C:\CSM",
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceRoot = Split-Path -Parent $ScriptDir

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host "CSM stable rollback: potrzebne uprawnienia administratora do zapisu w $InstallDir. Uruchamiam ponownie jako administrator..." -ForegroundColor Yellow
    $argsList = @('-NoProfile','-ExecutionPolicy','Bypass','-File', ('"' + $PSCommandPath + '"'), '-InstallDir', ('"' + $InstallDir + '"'))
    if ($NoRestart) { $argsList += '-NoRestart' }
    Start-Process -FilePath powershell.exe -ArgumentList ($argsList -join ' ') -Verb RunAs
    exit 0
}

if (-not (Test-Path -LiteralPath $InstallDir)) {
    throw "Nie znaleziono instalacji CSM: $InstallDir"
}
if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot 'addin\taskpane.js'))) {
    throw "Nie znaleziono plikow zrodlowych stabilnej poprawki w: $SourceRoot"
}

Write-Host "CSM stable rollback / panel fix" -ForegroundColor Cyan
Write-Host "Zrodlo:     $SourceRoot"
Write-Host "Instalacja: $InstallDir"

$stopScript = Join-Path $InstallDir 'tools\stop-claude-safe-mode.ps1'
if (-not $NoRestart -and (Test-Path -LiteralPath $stopScript)) {
    Write-Host "Zatrzymuje lokalne procesy CSM..." -ForegroundColor Cyan
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $stopScript | Out-Host
    } catch {
        Write-Warning "Nie udalo sie zatrzymac CSM automatycznie: $($_.Exception.Message)"
    }
}

# Zamknij Worda, bo WebView2 potrafi trzymac stary taskpane.js w cache.
try {
    Get-Process WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 700
} catch {}

$dirs = @('addin', 'server', 'tools', 'assets')
foreach ($dir in $dirs) {
    $src = Join-Path $SourceRoot $dir
    $dst = Join-Path $InstallDir $dir
    if (Test-Path -LiteralPath $src) {
        Write-Host "Aktualizuje $dir..." -ForegroundColor Cyan
        if (-not (Test-Path -LiteralPath $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
        Copy-Item -LiteralPath (Join-Path $src '*') -Destination $dst -Recurse -Force
    }
}

foreach ($file in @('README.md','README-EASY-START.md','LICENSE.txt','RELEASE-NOTES-v1.0.txt','docs/dev-reports/CSM_RC17_STABLE_PANEL_ROLLBACK_REPORT.md')) {
    $src = Join-Path $SourceRoot $file
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $InstallDir $file) -Force
    }
}

Write-Host "Stabilna poprawka panelu zostala skopiowana." -ForegroundColor Green
Write-Host "Wazne: otworz Worda dopiero po ponownym uruchomieniu CSM. Nie instaluj starego setup.exe na ta wersje." -ForegroundColor Yellow

$startScript = Join-Path $InstallDir 'tools\start-claude-safe-mode.ps1'
if (-not $NoRestart -and (Test-Path -LiteralPath $startScript)) {
    Write-Host "Uruchamiam CSM ponownie..." -ForegroundColor Cyan
    try {
        Start-Process -FilePath powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File', $startScript, '-NoOpenWord', '-NonInteractive') -WorkingDirectory $InstallDir
    } catch {
        Write-Warning "Nie udalo sie uruchomic CSM automatycznie: $($_.Exception.Message)"
        Write-Host "Uruchom recznie: $InstallDir\tools\start-claude-safe-mode.cmd" -ForegroundColor Yellow
    }
}

Write-Host "Gotowe. Teraz otworz Worda i panel CSM." -ForegroundColor Green
