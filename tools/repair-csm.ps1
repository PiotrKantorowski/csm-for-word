param([string]$InstallDir = "C:\CSM")
$ErrorActionPreference = "Stop"
$psExe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { (Get-Command pwsh).Source } else { "powershell.exe" }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallScript = Join-Path $ScriptDir "install-csm.ps1"
$SetupScript   = Join-Path $ScriptDir "setup-once.ps1"
$VenvPython    = Join-Path $InstallDir "server\.venv\Scripts\python.exe"
$LicenseAccepted = Join-Path $InstallDir ".license-accepted"

Write-Host "CSM NAPRAW — sprawdzam stan instalacji..." -ForegroundColor Cyan

# RC17: if .venv is missing OR imports fail (corrupt .venv), run setup-once first.
# This repairs the half-installed state (Machine A: Python 3.14, broken .venv, etc.)
$venvOk = $false
if (Test-Path -LiteralPath $VenvPython) {
    try {
        & $VenvPython -c "import fastapi, uvicorn, pydantic, lxml.etree" 2>$null
        $venvOk = ($LASTEXITCODE -eq 0)
    } catch { $venvOk = $false }
}
if (-not $venvOk) {
    $reason = if (Test-Path -LiteralPath $VenvPython) { "importy wymaganych modulow nie przechodza" } else { "plik nie istnieje" }
    Write-Host ".venv nie jest gotowe ($reason) — uruchamiam setup-once.ps1 -AcceptLicense..." -ForegroundColor Yellow
    if (-not (Test-Path -LiteralPath $SetupScript)) {
        Write-Host "BLAD: brak pliku $SetupScript" -ForegroundColor Red
        exit 1
    }
    & $psExe -NoProfile -ExecutionPolicy Bypass -File $SetupScript -SkipShareHint -AcceptLicense
    if ($LASTEXITCODE -ne 0) {
        Write-Host "BLAD: setup-once.ps1 zakonczyl sie bledem podczas naprawy (kod $LASTEXITCODE)." -ForegroundColor Red
        Write-Host "Sprawdz log: $env:TEMP\CSM-setup-once.log" -ForegroundColor Yellow
        Write-Host "Jesli brak Pythona 3.12 — pobierz z https://www.python.org/downloads/release/python-31210/ i uruchom NAPRAW ponownie." -ForegroundColor Yellow
        if (-not $NonInteractive) { Read-Host "Nacisnij Enter, aby zamknac" }
        exit 1
    }
    Write-Host "setup-once.ps1 zakonczyl sie sukcesem." -ForegroundColor Green
} else {
    Write-Host ".venv OK (importy przechodza) — pomijam setup-once, odswiezam tylko udzial/TrustedCatalog/cache." -ForegroundColor Green
}

# Run the catalog/share/shortcut/autostart refresh (with SkipDependencies since .venv is
# now either present or was just created above).
& $psExe -NoProfile -ExecutionPolicy Bypass -File $InstallScript -InstallDir $InstallDir -SkipDependencies -AcceptLicense
if ($LASTEXITCODE -ne 0) {
    Write-Host "OSTRZEZENIE: faza odswiezania katalogu/udzialu zakonczyla sie bledem (kod $LASTEXITCODE)." -ForegroundColor Yellow
    Write-Host "Jesli Word nadal nie widzi dodatku: Wstawianie -> Moje dodatki -> Folder udostepniony -> Odswiez." -ForegroundColor Yellow
} else {
    Write-Host "Naprawa zakonczona." -ForegroundColor Cyan
}
