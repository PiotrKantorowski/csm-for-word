param([switch]$SkipShareHint, [switch]$FromInstaller, [switch]$AcceptLicense, [string]$BielikModel = "")

# One-time setup for CSM for Word.
# This script runs in the target user's profile. It intentionally does not
# require Node and never compiles Python packages from source.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$ToolsDir = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { $ScriptDir } else { Join-Path $Root "tools" }
$ServerDir = Join-Path $Root "server"
$VenvDir = Join-Path $ServerDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$LicenseFile = Join-Path $Root "LICENSE.txt"
$LicenseAccepted = Join-Path $Root ".license-accepted"
$RuntimeRequirements = Join-Path $ServerDir "requirements-runtime.txt"
$WheelhouseDir = Join-Path $ServerDir "wheelhouse"
$RecommendedPythonVersion = "3.12.10"
$RecommendedPythonUrl = "https://www.python.org/ftp/python/$RecommendedPythonVersion/python-$RecommendedPythonVersion-amd64.exe"
$SupportEmail = "csm@kancelariakantorowski.pl"
$SupportHint = "Jesli cos nie dziala, napisz na $SupportEmail - pomoze nam to rozwiazac Twoj problem."
$SetupLogPath    = Join-Path $env:TEMP "CSM-setup-once.log"
$ProgressFile    = Join-Path $env:TEMP "CSM-progress.json"
try { Set-Content -Path $SetupLogPath -Value @("CSM setup-once log", "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", "User: $([Security.Principal.WindowsIdentity]::GetCurrent().Name)", "") -Encoding UTF8 } catch { }

# Write a progress snapshot that the Inno Setup progress monitor reads every 500 ms.
# State values: checking | downloading | installing | done | error
function Write-InstallProgress {
    param(
        [int]   $Pct,
        [string]$Phase,
        [string]$Detail = "",
        [string]$State  = "installing"
    )
    $prefix = switch ($State) {
        "checking"    { "Sprawdzanie: " }
        "downloading" { "Pobieranie: " }
        "installing"  { "Instalowanie: " }
        "done"        { "Gotowe." }
        "error"       { "Blad: " }
        default       { "" }
    }
    $detailText = if ($Detail) { "$prefix$Detail" } else { $prefix.TrimEnd() }
    # Escape for inline JSON (no external dependency)
    $phaseSafe  = $Phase      -replace '"', "'" -replace '\\', '/'
    $detailSafe = $detailText -replace '"', "'" -replace '\\', '/'
    $json = "{`"pct`":$Pct,`"phase`":`"$phaseSafe`",`"detail`":`"$detailSafe`",`"state`":`"$State`"}"
    try { [System.IO.File]::WriteAllText($ProgressFile, $json, [System.Text.Encoding]::UTF8) } catch { }
}

function Write-Info([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::White) {
    Write-Host $Message -ForegroundColor $Color
    try {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $SetupLogPath -Value "[$stamp] $Message" -Encoding UTF8
    } catch { }
}

function Write-SupportHint {
    Write-Info $SupportHint Yellow
}

# Always end setup failures with a human support route. This is especially
# important on fresh Windows installations where Python, winget, TLS/proxy,
# scheduled tasks or Office policy can differ from the developer machine.
$script:CsmSetupTrapActive = $true
trap {
    try {
        Write-Host ""
        Write-Info "[CSM] Konfiguracja jednorazowa zakonczyla sie bledem." Red
        if ($_.Exception -and $_.Exception.Message) {
            Write-Info ("Powod: " + $_.Exception.Message) Red
        }
        Write-SupportHint
    } catch { }
    exit 1
}

function Require-LicenseAcceptance {
    Write-Host ""
    Write-Info "Licencja CSM for Word" Cyan
    Write-Info "Przed instalacja musisz zaakceptowac warunki licencji." Yellow
    if (Test-Path $LicenseFile) {
        Write-Host ""
        Get-Content $LicenseFile -Encoding UTF8 | ForEach-Object { Write-Host $_ }
        Write-Host ""
        Write-Info "Pelna tresc licencji znajduje sie w: $LicenseFile" Yellow
    }
    $answer = Read-Host "Aby kontynuowac instalacje, wpisz AKCEPTUJE"
    if ($answer -ne "AKCEPTUJE") {
        throw "Licencja nie zostala zaakceptowana. Instalacja przerwana."
    }
    Set-Content -Path $LicenseAccepted -Value ("accepted_at=" + (Get-Date).ToString("s")) -Encoding UTF8
}

function Quote-ProcessArgument([string]$Argument) {
    if ($null -eq $Argument) { return '""' }
    $arg = [string]$Argument
    if ($arg -match '[\s"]') {
        return '"' + $arg.Replace('"', '\"') + '"'
    }
    return $arg
}

function Invoke-ProcessChecked {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$Description = $FilePath,
        [string]$WorkingDirectory = "",
        [int]$TimeoutSeconds = 0
    )

    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    $oldLocation = Get-Location
    if ($WorkingDirectory) { Set-Location -LiteralPath $WorkingDirectory }
    try {
        $argumentLine = (($Arguments | ForEach-Object { Quote-ProcessArgument ([string]$_) }) -join " ")
        Write-Info "Uruchamiam: $Description" DarkGray
        $proc = Start-Process -FilePath $FilePath -ArgumentList $argumentLine -NoNewWindow -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        if ($TimeoutSeconds -gt 0) {
            if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
                try { $proc.Kill() } catch { }
                try { $proc.WaitForExit(3000) | Out-Null } catch { }
                throw "$Description przekroczyl limit czasu $TimeoutSeconds s. Instalacja zostala przerwana, aby nie zostawiac uzytkownika z wiszacym paskiem postepu. Log: $SetupLogPath"
            }
        }
        # Always call WaitForExit() without timeout to flush async I/O and populate ExitCode.
        # Required on PowerShell 5.1 / .NET Framework: WaitForExit(ms) does not guarantee
        # ExitCode is set — only the no-arg overload does.
        $proc.WaitForExit()
        $exitCode = if ($null -ne $proc.ExitCode) { [int]$proc.ExitCode } else { 0 }
        $lines = @()
        foreach ($file in @($stdoutFile, $stderrFile)) {
            if (Test-Path -LiteralPath $file) {
                try { $lines += Get-Content -LiteralPath $file -Encoding UTF8 -ErrorAction SilentlyContinue } catch {
                    try { $lines += Get-Content -LiteralPath $file -Encoding OEM -ErrorAction SilentlyContinue } catch { }
                }
            }
        }
        foreach ($line in $lines) {
            if ($null -ne $line -and ([string]$line).Trim()) { Write-Info ([string]$line) DarkGray }
        }
        if ($exitCode -ne 0) {
            throw "$Description zakonczyl sie bledem. Kod wyjscia: $exitCode. Log: $SetupLogPath"
        }
    } finally {
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
        if ($WorkingDirectory) { Set-Location -LiteralPath $oldLocation }
    }
}

function Get-PythonInfo {
    param([Parameter(Mandatory=$true)][string]$Command, [string[]]$PrefixArgs = @())
    try {
        $code = "import sys,struct; print('%s.%s.%s|%s|%s'%(sys.version_info[0],sys.version_info[1],sys.version_info[2],sys.executable,8*struct.calcsize('P')))"
        $out = & $Command @PrefixArgs -c $code 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $parts = ([string]$out).Trim().Split('|')
        if ($parts.Count -lt 3) { return $null }
        if ($parts[1] -match "\\WindowsApps\\") { return $null }
        $versionParts = $parts[0].Split('.') | ForEach-Object { [int]$_ }
        return [pscustomobject]@{
            Command = $Command
            Args = $PrefixArgs
            Version = $parts[0]
            Major = $versionParts[0]
            Minor = $versionParts[1]
            Exe = $parts[1]
            Bits = [int]$parts[2]
        }
    } catch { return $null }
}

function Test-CompatiblePythonInfo {
    param($Info)
    if (-not $Info) { return $false }
    if ($Info.Major -ne 3) { return $false }
    if ($Info.Minor -ne 12) { return $false }
    if ($Info.Bits -ne 64) { return $false }
    return $true
}

function Add-PathCandidate([System.Collections.ArrayList]$List, [string]$Path) {
    if ($Path -and (Test-Path -LiteralPath $Path)) { [void]$List.Add(@($Path, @())) }
}

function Get-PythonCandidates {
    $candidates = [System.Collections.ArrayList]::new()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($ver in @("-3.12")) { [void]$candidates.Add(@("py", @($ver))) }
    }
    # PowerShell 5 treats a comma after an unparenthesized command argument as
    # part of that command's argument list. Keep each Join-Path call as its own
    # parenthesized expression and do not use comma separators here.
    $localPythonRoot = if ($env:LOCALAPPDATA) { Join-Path -Path ([string]$env:LOCALAPPDATA) -ChildPath "Programs\Python" } else { "" }
    $roots = @(
        $localPythonRoot
        "C:\Program Files\Python312"
    )
    foreach ($rootPath in $roots) {
        if (-not $rootPath -or -not (Test-Path -LiteralPath $rootPath)) { continue }
        if ((Split-Path -Leaf $rootPath) -match '^Python\d+$') {
            Add-PathCandidate $candidates (Join-Path $rootPath "python.exe")
        } else {
            Get-ChildItem -LiteralPath $rootPath -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^Python312$' } | ForEach-Object {
                Add-PathCandidate $candidates (Join-Path $_.FullName "python.exe")
            }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) { [void]$candidates.Add(@("python", @())) }
    if (Get-Command python3 -ErrorAction SilentlyContinue) { [void]$candidates.Add(@("python3", @())) }
    return $candidates
}

function Find-CompatiblePython {
    $seen = @{}
    foreach ($candidate in (Get-PythonCandidates)) {
        $info = Get-PythonInfo -Command $candidate[0] -PrefixArgs $candidate[1]
        if (-not $info) { continue }
        $key = $info.Exe.ToLowerInvariant()
        if ($seen.ContainsKey($key)) { continue }
        $seen[$key] = $true
        if (Test-CompatiblePythonInfo $info) { return $info }
        Write-Info "Pominieto niekompatybilny Python $($info.Version) ($($info.Bits)-bit): $($info.Exe)" Yellow
    }
    return $null
}

function Install-PythonViaWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
    Write-Info "Probuje zainstalowac Python 3.12 przez winget..." Yellow
    Write-InstallProgress 8 "Python 3.12" "Pobieranie Python 3.12 przez winget (~25 MB)..." "downloading"
    try {
        Invoke-ProcessChecked -FilePath "winget" -Arguments @(
            "install", "--id", "Python.Python.3.12", "-e", "--source", "winget",
            "--accept-package-agreements", "--accept-source-agreements", "--silent"
        ) -Description "Instalacja Python 3.12 przez winget" -TimeoutSeconds 900
        Write-InstallProgress 20 "Python 3.12" "Python 3.12 zainstalowany przez winget." "done"
        return $true
    } catch {
        Write-Info "Winget nie zainstalowal Pythona: $($_.Exception.Message)" Yellow
        return $false
    }
}

function Install-PythonViaPythonOrg {
    Write-Info "Probuje pobrac Python $RecommendedPythonVersion z python.org..." Yellow
    Write-InstallProgress 10 "Python 3.12" "Pobieranie instalatora Python $RecommendedPythonVersion z python.org (~25 MB)..." "downloading"
    $installer = Join-Path $env:TEMP "python-$RecommendedPythonVersion-amd64.exe"
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $RecommendedPythonUrl -OutFile $installer -UseBasicParsing -TimeoutSec 180
        Write-InstallProgress 18 "Python 3.12" "Instalowanie Python $RecommendedPythonVersion..." "installing"
        Invoke-ProcessChecked -FilePath $installer -Arguments @(
            "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_launcher=1", "Include_pip=1", "Include_test=0"
        ) -Description "Instalacja Python $RecommendedPythonVersion z python.org" -TimeoutSeconds 900
        Write-InstallProgress 23 "Python 3.12" "Python $RecommendedPythonVersion zainstalowany." "done"
        return $true
    } catch {
        Write-Info "Nie udalo sie pobrac lub zainstalowac Pythona z python.org: $($_.Exception.Message)" Yellow
        return $false
    }
}


function Get-WheelhousePipArgs {
    param(
        [Parameter(Mandatory=$true)][string]$RequirementsFile,
        [switch]$ForceReinstall
    )
    $wheelCount = 0
    if (Test-Path -LiteralPath $WheelhouseDir) {
        try { $wheelCount = @(Get-ChildItem -LiteralPath $WheelhouseDir -Filter "*.whl" -File -ErrorAction SilentlyContinue).Count } catch { $wheelCount = 0 }
    }
    $args = @("-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir")
    if ($ForceReinstall) { $args += "--force-reinstall" }
    if ($wheelCount -gt 0) {
        Write-Info "Znaleziono lokalne paczki Python wheelhouse ($wheelCount plikow). Instaluje bez pobierania z internetu." Green
        return $args + @("--no-index", "--find-links", $WheelhouseDir, "--only-binary=:all:", "--prefer-binary", "-r", $RequirementsFile)
    }
    Write-Info "Nie znaleziono lokalnego wheelhouse. Instaluje zaleznosci Python z PyPI." Yellow
    return $args + @("--only-binary=:all:", "--prefer-binary", "-r", $RequirementsFile)
}

function Get-WheelhouseBootstrapArgs {
    $wheelCount = 0
    $hasPipWheel = $false
    if (Test-Path -LiteralPath $WheelhouseDir) {
        try {
            $wheels = @(Get-ChildItem -LiteralPath $WheelhouseDir -Filter "*.whl" -File -ErrorAction SilentlyContinue)
            $wheelCount = $wheels.Count
            $hasPipWheel = @(($wheels | Where-Object { $_.Name -match '^pip-' })).Count -gt 0
        } catch { $wheelCount = 0; $hasPipWheel = $false }
    }
    if ($wheelCount -gt 0 -and $hasPipWheel) {
        return @("-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--no-index", "--find-links", $WheelhouseDir, "--upgrade", "pip", "setuptools", "wheel")
    }
    if ($wheelCount -gt 0) {
        Write-Info "Wheelhouse nie zawiera paczki pip. Pomijam aktualizacje pip i uzywam pip z ensurepip." Yellow
        return @("-m", "pip", "--version")
    }
    return @("-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir", "--upgrade", "pip", "setuptools", "wheel")
}

function Refresh-PathFromRegistry {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath;$env:Path"
}

# ─── Ollama + Bielik auto-setup ───────────────────────────────────────────────

$BielikDefaultModel = if ($BielikModel -ne "") { $BielikModel } else { "hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M" }

function Install-OllamaViaWinget {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
    Write-Info "Instaluje Ollama przez winget (moze potrwac kilka minut)..." Yellow
    try {
        Invoke-ProcessChecked -FilePath "winget" -Arguments @(
            "install", "--id", "Ollama.Ollama", "-e", "--source", "winget",
            "--accept-package-agreements", "--accept-source-agreements", "--silent"
        ) -Description "Instalacja Ollama" -TimeoutSeconds 600
        Refresh-PathFromRegistry
        return $null -ne (Get-Command ollama -ErrorAction SilentlyContinue)
    } catch {
        Write-Info "Winget nie zainstalowal Ollama: $($_.Exception.Message)" Yellow
        return $false
    }
}

function Wait-OllamaApiReady([int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 600
    }
    return $false
}

function Get-OllamaModels {
    try {
        $json = (Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop).Content
        return ($json | ConvertFrom-Json).models
    } catch { return @() }
}

function Setup-OllamaAndBielik {
    Write-Info ""
    Write-Info "Konfiguracja analizy kontekstowej AI (Bielik + Ollama)..." Cyan

    # 1. Ensure Ollama is installed
    Write-InstallProgress 60 "Ollama" "Sprawdzam czy Ollama jest zainstalowana..." "checking"
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) {
        Write-Info "Ollama nie jest zainstalowana. Probuje zainstalowac przez winget..." Yellow
        Write-InstallProgress 62 "Ollama" "Pobieranie Ollama przez winget (~100 MB)..." "downloading"
        $installed = Install-OllamaViaWinget
        $ollama = Get-Command ollama -ErrorAction SilentlyContinue
        if (-not $ollama) {
            Write-Info "Nie udalo sie zainstalowac Ollama automatycznie." Yellow
            Write-Info "Zainstaluj Ollama recznie z https://ollama.com/ i uruchom ponownie CSM -> NAPRAW." Yellow
            Write-Info "CSM dziala normalnie bez Bielika — ta warstwa jest opcjonalna." Yellow
            Write-InstallProgress 68 "Ollama (pominiety)" "Ollama niedostepna — Bielik AI nie zostanie skonfigurowany. Zainstaluj recznie." "error"
            return
        }
        Write-InstallProgress 68 "Ollama" "Ollama zainstalowana pomyslnie." "done"
        Write-Info "Ollama zainstalowana: $($ollama.Source)" Green
    } else {
        Write-InstallProgress 68 "Ollama" "Ollama jest juz zainstalowana." "done"
        Write-Info "Ollama jest dostepna: $($ollama.Source)" Green
    }

    # 2. Start ollama serve if not running
    $ollamaRunning = $false
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        $ollamaRunning = ($r.StatusCode -eq 200)
    } catch { }

    if (-not $ollamaRunning) {
        Write-InstallProgress 69 "Ollama" "Uruchamiam serwer Ollama w tle..." "installing"
        Write-Info "Uruchamiam serwer Ollama w tle (do pobrania modelu)..." Yellow
        Start-Process -FilePath "ollama" -ArgumentList @("serve") -WindowStyle Hidden | Out-Null
        $ollamaRunning = Wait-OllamaApiReady -TimeoutSeconds 25
        if (-not $ollamaRunning) {
            Write-Info "Serwer Ollama nie odpowiada. Model zostanie pobrany przy nastepnym starcie CSM." Yellow
        }
    }

    # 3. Pull Bielik model if needed
    if ($ollamaRunning) {
        Write-InstallProgress 70 "Model Bielik" "Sprawdzam czy model Bielik jest juz dostepny lokalnie..." "checking"
        $models = Get-OllamaModels
        $bielikPresent = $null -ne ($models | Where-Object { $_.name -match "(?i)bielik" })
        if ($bielikPresent) {
            Write-InstallProgress 91 "Model Bielik" "Model Bielik jest juz dostepny lokalnie." "done"
            Write-Info "Model Bielik jest juz dostepny lokalnie." Green
        } else {
            Write-InstallProgress 72 "Model Bielik (~4 GB)" "Pobieranie Bielik-Minitron-7B... to jednorazowy download, moze potrwac kilka minut." "downloading"
            Write-Info "Pobieram model Bielik (~4 GB). To jednorazowy download; moze to potrwac kilka minut..." Yellow
            try {
                Invoke-ProcessChecked -FilePath "ollama" -Arguments @("pull", $BielikDefaultModel) -Description "Pobieranie modelu Bielik" -TimeoutSeconds 3600
                Write-InstallProgress 91 "Model Bielik" "Model Bielik pobrany i gotowy." "done"
                Write-Info "Model Bielik pobrany pomyslnie." Green
            } catch {
                Write-InstallProgress 91 "Model Bielik (blad)" "Nie udalo sie pobrac modelu. Uruchom recznie: ollama pull $BielikDefaultModel" "error"
                Write-Info "Nie udalo sie pobrac modelu Bielik: $($_.Exception.Message)" Yellow
                Write-Info "Pobierz go recznie: ollama pull $BielikDefaultModel" Yellow
                Write-Info "CSM uruchomi sie bez Bielika do czasu pobrania modelu." Yellow
            }
        }
    }

    # 4. Enable Bielik persistently in user environment
    Write-InstallProgress 93 "Konfiguracja AI" "Zapisuje ustawienia Bielik AI w profilu uzytkownika..." "installing"
    [Environment]::SetEnvironmentVariable("CSMW_ENABLE_BIELIK", "1", "User")
    $env:CSMW_ENABLE_BIELIK = "1"
    if (-not [Environment]::GetEnvironmentVariable("CSMW_BIELIK_MODEL", "User")) {
        [Environment]::SetEnvironmentVariable("CSMW_BIELIK_MODEL", $BielikDefaultModel, "User")
        $env:CSMW_BIELIK_MODEL = $BielikDefaultModel
    }
    Write-Info "Bielik AI skonfigurowany jako opcjonalna kontrola (CSMW_ENABLE_BIELIK=1 zapisane w profilu uzytkownika)." Green
    Write-Info "Standardowa anonimizacja nie uzywa Bielika; model uruchamia sie dopiero po wyborze trybu Bielik w panelu." Cyan
}

function Install-CompatiblePython {
    Write-Info "Nie znaleziono kompatybilnego Pythona 3.12 64-bit." Yellow
    Write-Info "CSM 1.0 wymaga Python 3.12, bo offline wheelhouse zawiera binarne wheels cp312." Yellow
    $ok = Install-PythonViaWinget
    Refresh-PathFromRegistry
    if (-not (Find-CompatiblePython)) {
        if (-not $ok) { $ok = Install-PythonViaPythonOrg }
        Refresh-PathFromRegistry
    }
    if (-not $ok) {
        Write-SupportHint
        throw "Nie udalo sie automatycznie zainstalowac Python 3.12. Zainstaluj Python 3.12 64-bit z https://www.python.org/downloads/release/python-31210/ i uruchom instalator CSM ponownie."
    }
}

function Ensure-CompatiblePython {
    $info = Find-CompatiblePython
    if (-not $info) {
        Install-CompatiblePython
        $info = Find-CompatiblePython
    }
    if (-not (Test-CompatiblePythonInfo $info)) {
        throw "Nie udalo sie znalezc kompatybilnego Pythona po instalacji. Wymagany jest Python 3.12 64-bit zgodny z offline wheelhouse cp312."
    }
    Write-Info "Uzywam Python $($info.Version) ($($info.Bits)-bit): $($info.Exe)" Green
    return $info
}

function Get-VenvInfo {
    if (-not (Test-Path -LiteralPath $PythonExe)) { return $null }
    return Get-PythonInfo -Command $PythonExe -PrefixArgs @()
}

function Remove-BrokenVenvIfNeeded {
    $venvInfo = Get-VenvInfo
    if (-not $venvInfo) { return }
    if (-not (Test-CompatiblePythonInfo $venvInfo)) {
        Write-Info "Istniejace srodowisko .venv uzywa Python $($venvInfo.Version). Usuwam je i tworze ponownie." Yellow
        Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
        return
    }
    try {
        & $PythonExe -c "import fastapi, uvicorn, pydantic, lxml.etree" 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Info "Istniejace srodowisko .venv jest niepelne. Usuwam je i tworze ponownie." Yellow
            Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    } catch {
        Write-Info "Istniejace srodowisko .venv jest uszkodzone. Usuwam je i tworze ponownie." Yellow
        Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}


function Repair-VenvPip {
    if (-not (Test-Path -LiteralPath $PythonExe)) { return $false }
    try {
        & $PythonExe -m pip --version 1>$null 2>$null
        if ($LASTEXITCODE -eq 0) { return $true }
    } catch { }
    Write-Info "Naprawiam pip w srodowisku .venv przez ensurepip..." Yellow
    try {
        Invoke-ProcessChecked -FilePath $PythonExe -Arguments @("-m", "ensurepip", "--upgrade") -Description "Naprawa pip w .venv" -TimeoutSeconds 300
        & $PythonExe -m pip --version 1>$null 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        Write-Info "ensurepip nie naprawil pip: $($_.Exception.Message)" Yellow
        return $false
    }
}

function Ensure-VenvCreated {
    param($SelectedPython)
    if (Test-Path -LiteralPath $PythonExe) {
        if (Repair-VenvPip) { return }
        Write-Info "Istniejace .venv ma uszkodzony pip. Usuwam je i tworze ponownie." Yellow
        Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    }

    Write-Info "Tworze srodowisko Python .venv..." Yellow
    try {
        Invoke-ProcessChecked -FilePath $SelectedPython.Command -Arguments ($SelectedPython.Args + @("-m", "venv", ".venv")) -Description "Tworzenie srodowiska Python .venv" -WorkingDirectory $ServerDir -TimeoutSeconds 300
    } catch {
        # Some Windows/Python installations create Scripts\python.exe and then
        # return a non-zero code because ensurepip has trouble. Do not leave the
        # user with a mysterious setup failure: attempt to repair pip first.
        if (-not (Test-Path -LiteralPath $PythonExe)) { throw }
        Write-Info "Venv zostal utworzony czesciowo. Probuje naprawic pip i kontynuowac..." Yellow
    }

    if (Repair-VenvPip) { return }

    Write-Info "Standardowe tworzenie .venv nie zapewnilo pip. Tworze .venv ponownie bez pip i uruchamiam ensurepip." Yellow
    Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
    Invoke-ProcessChecked -FilePath $SelectedPython.Command -Arguments ($SelectedPython.Args + @("-m", "venv", "--without-pip", ".venv")) -Description "Tworzenie .venv bez pip" -WorkingDirectory $ServerDir -TimeoutSeconds 300
    if (-not (Repair-VenvPip)) {
        throw "Nie udalo sie przygotowac pip w .venv. Sprawdz instalacje Pythona 3.12 albo uruchom instalator CSM ponownie po restarcie."
    }
}

Write-Info "CSM - konfiguracja jednorazowa" Cyan

if (Test-Path $LicenseAccepted) {
    Write-Info "Licencja byla juz zaakceptowana." Green
} elseif ($AcceptLicense -or $FromInstaller -or ($env:CSM_ACCEPT_LICENSE -eq '1')) {
    # License was accepted in the Inno Setup GUI, via explicit -AcceptLicense flag,
    # or via environment variable — never call Read-Host in a hidden/non-interactive context.
    $licSrc = if ($AcceptLicense) { "installer-switch" } elseif ($FromInstaller) { "installer-gui" } else { "env-variable" }
    Set-Content -Path $LicenseAccepted -Value ("accepted_at=" + (Get-Date).ToString("s") + ";source=" + $licSrc) -Encoding UTF8
    Write-Info "Licencja zaakceptowana (zrodlo: $licSrc)." Green
} elseif ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
    Require-LicenseAcceptance
} else {
    throw "Licencja nie zostala zaakceptowana i brak flagi -AcceptLicense / -FromInstaller. W trybie nieinteraktywnym wymagana jest flaga -AcceptLicense lub zmienna CSM_ACCEPT_LICENSE=1."
}

# Beta warning — shown after license acceptance on every fresh setup
Write-Host ""
Write-Info "*** WERSJA BETA — WAZNA INFORMACJA ***" Yellow
Write-Info "Przed przekazaniem pliku do Claude lub innego modelu AI ZAWSZE sprawdz" Yellow
Write-Info "zanonimizowany dokument (_CSM_anon.docx) i upewnij sie, ze wszystkie" Yellow
Write-Info "dane osobowe i poufne zostaly prawidlowo zastapione pseudonimami." Yellow
Write-Info "CSM jest narzedziem wspomagajacym — weryfikacja nalezy do uzytkownika." Yellow
Write-Host ""

Write-InstallProgress 5 "Python 3.12" "Szukam kompatybilnej instalacji Pythona 3.12..." "checking"
$SelectedPython = Ensure-CompatiblePython
Remove-BrokenVenvIfNeeded

Write-InstallProgress 25 "Srodowisko Python (.venv)" "Tworze izolowane srodowisko wirtualne..." "installing"
Ensure-VenvCreated -SelectedPython $SelectedPython

if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Nie znaleziono python.exe w .venv po utworzeniu srodowiska: $PythonExe" }
if (-not (Repair-VenvPip)) { throw "pip w .venv nie dziala po utworzeniu srodowiska." }
if (-not (Test-Path -LiteralPath $RuntimeRequirements)) { throw "Brak pliku wymagan runtime: $RuntimeRequirements" }

Write-InstallProgress 33 "Pakiety Python" "Instaluje pakiety offline: fastapi, uvicorn, lxml, pydantic..." "installing"
Write-Info "Instaluje zaleznosci Python runtime..." Yellow
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_INPUT = "1"
Invoke-ProcessChecked -FilePath $PythonExe -Arguments (Get-WheelhouseBootstrapArgs) -Description "Aktualizacja pip" -TimeoutSeconds 600
Write-InstallProgress 38 "Pakiety Python" "Instaluje zaleznosci CSM (moze potrwac 1-2 min)..." "installing"
Invoke-ProcessChecked -FilePath $PythonExe -Arguments (Get-WheelhousePipArgs -RequirementsFile "requirements-runtime.txt") -Description "Instalacja zaleznosci Python runtime" -WorkingDirectory $ServerDir -TimeoutSeconds 900
try {
    & $PythonExe -c "import fastapi, uvicorn, pydantic, lxml.etree" 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw "brak wymaganych modulow po instalacji" }
} catch {
    Write-Info "Zaleznosci runtime nie sa kompletne po pierwszej probie. Ponawiam instalacje bez cache pip..." Yellow
    Write-InstallProgress 42 "Pakiety Python (ponowna instalacja)" "Ponawiam instalacje bez cache pip..." "installing"
    Invoke-ProcessChecked -FilePath $PythonExe -Arguments (Get-WheelhousePipArgs -RequirementsFile "requirements-runtime.txt" -ForceReinstall) -Description "Ponowna instalacja zaleznosci Python runtime" -WorkingDirectory $ServerDir -TimeoutSeconds 900
}

Write-InstallProgress 52 "Certyfikat HTTPS localhost" "Przygotowuje zaufany certyfikat SSL dla panelu Word..." "installing"
Write-Info "Przygotowuje certyfikat HTTPS localhost dla dodatku Word..." Yellow
$certScript = Join-Path $ToolsDir "ensure-localhost-cert.ps1"
if (-not (Test-Path -LiteralPath $certScript)) { throw "Brak skryptu certyfikatu localhost: $certScript" }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $certScript
if ($LASTEXITCODE -ne 0) { throw "Nie udalo sie przygotowac certyfikatu HTTPS localhost." }

Write-InstallProgress 56 "Weryfikacja CSM" "Sprawdzam poprawnosc instalacji (szybki autotest)..." "checking"
Write-Info "Uruchamiam szybki autotest lokalnego anonimizatora..." Yellow
$smoke = "import fastapi,uvicorn,pydantic,lxml.etree; import api; print('CSM smoke import OK')"
Invoke-ProcessChecked -FilePath $PythonExe -Arguments @("-c", $smoke) -Description "Autotest importu CSM" -WorkingDirectory $ServerDir -TimeoutSeconds 60

# RC18: desktop shortcut no longer created automatically.
# Use the service panel inside the Word add-in (START/STOP/NAPRAW/CLEAN/DIAGNOZA).
# create-desktop-shortcut.ps1 is still available for manual use.

Setup-OllamaAndBielik

Write-InstallProgress 98 "CSM v1.0" "Instalacja zakonczona. Mozesz otworzyc Worda." "done"
Write-Host ""
Write-Info "Konfiguracja zakonczona." Green
Write-Info "Log konfiguracji: $SetupLogPath" Cyan
Write-Info "Otworz Worda i uruchom panel CSM z karty Dodatki." Cyan
Write-Info "W razie problemow z CSM: $SupportHint" Yellow
Write-Host ""
if (-not $SkipShareHint) {
    Write-Info "Instalator automatycznie konfiguruje udzial Worda i zaufany katalog." Cyan
    Write-Info "Nie musisz recznie dodawac katalogu w Centrum zaufania Worda." Cyan
}

try {
    $Guide = Join-Path $Root "install-guide.html"
    if (Test-Path $Guide) {
        $GuideUrl = if ($FromInstaller) {
            "file:///" + $Guide.Replace("\", "/") + "?from=installer"
        } else {
            $Guide
        }
        Start-Process $GuideUrl
    }
} catch { }
