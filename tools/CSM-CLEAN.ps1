<#
CSM-CLEAN.ps1

Tryb ratunkowy dla dodatku CSM do Worda.
Zamyka Worda, czysci cache dodatkow Office/Word, wykonuje CSM - STOP,
a nastepnie CSM - START.

Uzywaj, gdy Word pokazuje stara wersje dodatku albo panel nie reaguje.
#>

param(
    [int]$WaitSeconds = 5,
    [switch]$Force,
    [switch]$SkipRestart
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$ToolsDir = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { $ScriptDir } else { Join-Path $Root "tools" }

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Confirm-Clean {
    if ($Force) { return $true }
    Write-Host ""
    Write-Host "CSM-CLEAN zamknie Worda i wyczysci cache dodatku Office/Word." -ForegroundColor Yellow
    Write-Host "Nie usuwa dokumentow ani plikow aplikacji CSM, ale Word moze ponownie ladowac dodatki." -ForegroundColor Yellow
    Write-Host ""
    $answer = Read-Host "Czy na pewno chcesz usunac CSM w Word / wyczyscic cache Worda? Wpisz TAK"
    return ($answer -eq "TAK")
}

function Clear-FolderContents {
    param([string]$PathToClear)

    if (-not (Test-Path -LiteralPath $PathToClear)) {
        Write-Host "[POMINIETO] Nie istnieje: $PathToClear" -ForegroundColor DarkYellow
        return
    }

    try {
        $items = Get-ChildItem -LiteralPath $PathToClear -Force -ErrorAction SilentlyContinue
        $count = 0
        foreach ($item in $items) {
            Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction Stop
            $count++
        }
        Write-Host "[OK] Wyczyszczono: $PathToClear ($count elementow)" -ForegroundColor Green
    }
    catch {
        Write-Host "[BLAD] Nie udalo sie wyczyscic: $PathToClear" -ForegroundColor Red
        Write-Host "      $($_.Exception.Message)" -ForegroundColor Red
    }
}

function Start-ScriptIfExists {
    param(
        [string]$ScriptName,
        [string]$Label,
        [string[]]$ExtraArgs = @()
    )

    $PathToStart = Join-Path $ToolsDir $ScriptName
    if (-not (Test-Path -LiteralPath $PathToStart)) {
        Write-Host "[POMINIETO] Nie znaleziono: $ScriptName" -ForegroundColor DarkYellow
        return $false
    }

    try {
        Write-Host "[START] $Label" -ForegroundColor Green
        $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $PathToStart) + $ExtraArgs
        Start-Process -FilePath "powershell.exe" -ArgumentList $args -WorkingDirectory $Root
        return $true
    }
    catch {
        Write-Host "[BLAD] Nie udalo sie uruchomic: $Label" -ForegroundColor Red
        Write-Host "      $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

Write-Host "CSM-CLEAN" -ForegroundColor White
Write-Host "Awaryjne czyszczenie cache Word/Office i restart CSM." -ForegroundColor White

if (-not (Confirm-Clean)) {
    Write-Host "Anulowano CSM-CLEAN." -ForegroundColor Yellow
    exit 0
}

Write-Step "Zamykanie Worda"
$wordProcesses = Get-Process -Name WINWORD -ErrorAction SilentlyContinue
if ($wordProcesses) {
    foreach ($proc in $wordProcesses) {
        try {
            Write-Host "[STOP] WINWORD.EXE PID=$($proc.Id)"
            Stop-Process -Id $proc.Id -Force -ErrorAction Stop
        }
        catch {
            Write-Host "[BLAD] Nie udalo sie zamknac WINWORD.EXE PID=$($proc.Id): $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    Start-Sleep -Seconds 2
}
else {
    Write-Host "[OK] Word nie jest uruchomiony." -ForegroundColor Green
}

Write-Step "Czyszczenie cache Office"
$officeBase = Join-Path $env:LOCALAPPDATA "Microsoft\Office\16.0"
$cachePaths = @(
    (Join-Path $officeBase "Wef"),
    (Join-Path $officeBase "WebServiceCache"),
    (Join-Path $officeBase "OfficeFileCache")
)

foreach ($path in $cachePaths) {
    Clear-FolderContents -PathToClear $path
}

if (-not $SkipRestart) {
    Write-Step "Restart CSM"
    Start-ScriptIfExists -ScriptName "stop-claude-safe-mode.ps1" -Label "CSM - STOP" | Out-Null
    Write-Host "[INFO] Czekam $WaitSeconds sekund..."
    Start-Sleep -Seconds $WaitSeconds
    Start-ScriptIfExists -ScriptName "start-claude-safe-mode.ps1" -Label "CSM - START" -ExtraArgs @("-NoOpenWord", "-NonInteractive") | Out-Null
}

Write-Step "Koniec"
Write-Host "CSM zostal ponownie uruchomiony w tle. Teraz otworz Worda i wczytaj dodatek CSM." -ForegroundColor White
Write-Host "Zaufany katalog Worda pozostaje: \\localhost\ClaudeSafeModeAddin\" -ForegroundColor White
