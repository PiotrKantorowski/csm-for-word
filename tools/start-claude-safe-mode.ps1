# CSM for Word - one-click launcher
# Starts both local services required by the Word add-in.

param(
    [switch]$NoOpenWord,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$ToolsDir = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { $ScriptDir } else { Join-Path $Root "tools" }
$ServerDir = Join-Path $Root "server"
$AddinDir = Join-Path $Root "addin"
$PythonExe = Join-Path $ServerDir ".venv\Scripts\python.exe"
$LicenseAccepted = Join-Path $Root ".license-accepted"
$RuntimeDir = Join-Path $Root "runtime"
$TokenFile = Join-Path $RuntimeDir "api-token.txt"
$AddinTokenFile = Join-Path $AddinDir "csm-token.js"
$CertDir = Join-Path $env:USERPROFILE ".office-addin-dev-certs"
$CertFile = Join-Path $CertDir "localhost.crt"
$KeyFile = Join-Path $CertDir "localhost.key"
$LogsDir = Join-Path $Root "logs"
$SupportEmail = "csm@kancelariakantorowski.pl"
$SupportHint = "Jesli cos nie dziala, napisz na $SupportEmail - pomoze nam to rozwiazac Twoj problem."
$BackendLog = Join-Path $LogsDir "backend-8787.log"
$AddinLog = Join-Path $LogsDir "addin-3000.log"
$AddinStaticServer = Join-Path $ServerDir "static_addin_server.py"
$BackendPidFile = Join-Path $RuntimeDir "backend-wrapper.pid"
$AddinPidFile = Join-Path $RuntimeDir "addin-wrapper.pid"

function New-Token {
    $bytes = New-Object byte[] 32
    # Windows PowerShell 5.1 / older .NET do not support RandomNumberGenerator.Fill().
    # RNGCryptoServiceProvider works on Windows PowerShell 5.1 and PowerShell 7+.
    $rng = New-Object System.Security.Cryptography.RNGCryptoServiceProvider
    try {
        $rng.GetBytes($bytes)
    } finally {
        if ($null -ne $rng) { $rng.Dispose() }
    }
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_").TrimEnd("=")
}

function Write-Utf8NoBom([string]$Path, [string]$Value) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function Prepare-ApiToken {
    if (-not (Test-Path $RuntimeDir)) { New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null }
    $token = New-Token
    # Use UTF-8 without BOM. Windows PowerShell 5.1 Set-Content -Encoding UTF8
    # writes a BOM, which would become part of the backend token and break
    # X-CSM-Token comparisons. Keep the API token and add-in JS token perfectly aligned.
    Write-Utf8NoBom -Path $TokenFile -Value $token
    Write-Utf8NoBom -Path $AddinTokenFile -Value ("window.CSM_TOKEN = '{0}'; window.CSM_TOKEN_GENERATED_AT = '{1}';" -f $token, (Get-Date).ToString("o"))
}

function Test-PortOpen([int]$Port) {
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return $null -ne $conn
    } catch {
        return $false
    }
}


function Get-ProcessCommandLine([int]$ProcessId) {
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
        if ($proc) { return [string]$proc.CommandLine }
    } catch {}
    return ""
}

function Test-CsmOwnedProcess([int]$ProcessId) {
    $cmd = (Get-ProcessCommandLine $ProcessId)
    if (-not $cmd) { return $false }
    $rootNorm = $Root.ToLowerInvariant()
    $cmdNorm = $cmd.ToLowerInvariant()
    return ($cmdNorm.Contains($rootNorm) -or $cmdNorm.Contains("static_addin_server.py") -or $cmdNorm.Contains("uvicorn api:app") -or $cmdNorm.Contains("csm"))
}

function Stop-PortProcesses([int]$Port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        $processIds = @($conns | Select-Object -ExpandProperty OwningProcess -Unique)
        foreach ($procId in $processIds) {
            if ($procId -and $procId -ne $PID) {
                if (Test-CsmOwnedProcess -ProcessId $procId) {
                    try {
                        Write-Host "Zatrzymuje stary proces CSM na porcie $Port (PID $procId), aby uniknac cache/starego tokenu." -ForegroundColor Yellow
                        Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                    } catch {}
                } else {
                    $cmd = Get-ProcessCommandLine $procId
                    throw "Port $Port jest zajety przez inny proces (PID $procId). Zamknij ten program albo zwolnij port i uruchom CSM ponownie. $cmd"
                }
            }
        }
    } catch { throw }
}


function Wait-HttpReady([string]$Url, [int]$TimeoutSeconds, [string]$Label, [switch]$IgnoreCertificateErrors) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $lastError = ""
    $oldCallback = $null
    if ($IgnoreCertificateErrors) {
        try {
            $oldCallback = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        } catch {}
    }
    try {
        while ((Get-Date) -lt $deadline) {
            try {
                $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
                if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
                    Write-Host "$Label odpowiada: HTTP $($response.StatusCode)" -ForegroundColor Green
                    return $true
                }
                $lastError = "HTTP $($response.StatusCode)"
            } catch {
                $lastError = $_.Exception.Message
            }
            Start-Sleep -Milliseconds 750
        }
    } finally {
        if ($IgnoreCertificateErrors) {
            try { [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $oldCallback } catch {}
        }
    }
    Write-Host "OSTRZEZENIE: $Label nie odpowiedzial w ciagu $TimeoutSeconds s. $lastError" -ForegroundColor Yellow
    return $false
}

function Wait-TcpReady([int]$Port, [int]$TimeoutSeconds, [string]$Label) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen $Port) {
            Write-Host "$Label nasluchuje na porcie $Port." -ForegroundColor Green
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "OSTRZEZENIE: $Label nie otworzyl portu $Port w ciagu $TimeoutSeconds s." -ForegroundColor Yellow
    return $false
}

function Ensure-LogDirs {
    foreach ($dir in @($RuntimeDir, $LogsDir)) {
        if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    }
}

function Write-ProcessId([string]$Path, [int]$ProcessId) {
    try { Set-Content -Path $Path -Value ([string]$ProcessId) -Encoding ASCII } catch {}
}

function Test-LocalAuth {
    try {
        $token = if (Test-Path -LiteralPath $TokenFile) { [System.IO.File]::ReadAllText($TokenFile).Trim() } else { "" }
        if (-not $token) {
            Write-Host "BLAD: brak pliku tokenu API: $TokenFile" -ForegroundColor Red
            return $false
        }
        $headers = @{ "X-CSM-Token" = $token }
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:8787/auth_check" -Method Post -Headers $headers -ContentType "application/json" -Body "{}" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300) {
            Write-Host "Token API zweryfikowany z backendem." -ForegroundColor Green
            return $true
        }
    } catch {
        Write-Host "BLAD: token API nie przeszedl lokalnego testu: $($_.Exception.Message)" -ForegroundColor Red
    }
    return $false
}


function Write-LogTail([string]$Path, [int]$Lines = 40) {
    try {
        if (Test-Path -LiteralPath $Path) {
            Write-Host "--- Ostatnie linie logu: $Path ---" -ForegroundColor DarkYellow
            Get-Content -LiteralPath $Path -Tail $Lines -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host $_ -ForegroundColor DarkYellow
            }
            Write-Host "--- koniec logu ---" -ForegroundColor DarkYellow
        }
    } catch {}
}

function Test-AddinFilesReady {
    foreach ($name in @("taskpane.html", "taskpane.js", "word-bridge.js", "state-machine.js", "csm-token.js")) {
        $path = Join-Path $AddinDir $name
        if (-not (Test-Path -LiteralPath $path)) {
            Write-Host "BLAD: brak pliku dodatku Word: $path" -ForegroundColor Red
            return $false
        }
    }
    return $true
}

function Ensure-OllamaRunning {
    # Always try to start Ollama if it is installed — no env var gate needed.
    # If Ollama is not installed at all, skip silently (no message).
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) { return }

    # Check if already running
    $running = $false
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        $running = ($r.StatusCode -eq 200)
    } catch { }

    if (-not $running) {
        Write-Host "Bielik AI: uruchamiam Ollama w tle..." -ForegroundColor Yellow
        Start-Process -FilePath "ollama" -ArgumentList @("serve") -WindowStyle Hidden | Out-Null
        $deadline = (Get-Date).AddSeconds(20)
        while ((Get-Date) -lt $deadline) {
            try {
                $r = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
                if ($r.StatusCode -eq 200) { $running = $true; break }
            } catch { }
            Start-Sleep -Milliseconds 600
        }
    }

    # Mark Bielik as available for the optional deep-review button. Standard
    # anonymization does not call Bielik; the backend uses it only when the user
    # chooses review_mode=bielik in the panel.
    $env:CSMW_ENABLE_BIELIK = "1"
    $bielikModel = $env:CSMW_BIELIK_MODEL
    if (-not $bielikModel) {
        $bielikModel = [Environment]::GetEnvironmentVariable("CSMW_BIELIK_MODEL", "User")
        if ($bielikModel) { $env:CSMW_BIELIK_MODEL = $bielikModel }
    }

    if ($running) {
        Write-Host "Bielik AI: dostepny jako opcjonalna kontrola." -ForegroundColor Green
    } else {
        Write-Host "Bielik AI: Ollama startuje wolno — standardowa anonimizacja dziala bez Bielika." -ForegroundColor Yellow
    }
}

function Invoke-SelfHealSetupOnce {
    # RC17 self-heal: if .venv is missing but license was already accepted (i.e.
    # previous install was interrupted after catalog registration), re-run
    # setup-once.ps1 silently before trying to start services.
    $setupScript = Join-Path $ToolsDir "setup-once.ps1"
    if (-not (Test-Path -LiteralPath $setupScript)) {
        Write-Host "Nie mozna przeprowadzic samoleczenia: brak $setupScript" -ForegroundColor Yellow
        return $false
    }
    Write-Host "Wykryto brak .venv — uruchamiam samoleczenie (setup-once.ps1 -AcceptLicense)..." -ForegroundColor Yellow
    try {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setupScript -SkipShareHint -AcceptLicense
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Samoleczenie (setup-once.ps1) zakonczylo sie bledem (kod $LASTEXITCODE). Sprawdz logi." -ForegroundColor Red
            return $false
        }
        if (Test-Path -LiteralPath $PythonExe) {
            Write-Host "Samoleczenie zakonczone sukcesem — .venv odtworzone." -ForegroundColor Green
            return $true
        }
        Write-Host "Samoleczenie uruchomilo sie bez bledu, ale .venv nadal brak." -ForegroundColor Red
        return $false
    } catch {
        Write-Host "Samoleczenie nie udalo sie: $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

function Start-Backend {
    Ensure-LogDirs
    if (Test-PortOpen 8787) {
        Stop-PortProcesses 8787
        Start-Sleep -Milliseconds 800
    }
    if (-not (Test-Path $PythonExe)) {
        if (Test-Path $LicenseAccepted) {
            $healed = Invoke-SelfHealSetupOnce
            if (-not $healed -or -not (Test-Path $PythonExe)) {
                throw "Nie znaleziono $PythonExe nawet po samoleczeniu. Uzyj ikony CSM -> NAPRAW albo uruchom ponownie setup-once.ps1."
            }
        } else {
            throw "Nie znaleziono $PythonExe. Uruchom najpierw setup-once.ps1 (setup-once.cmd) lub zainstaluj CSM ponownie."
        }
    }
    "[$((Get-Date).ToString('s'))] START backend" | Out-File -FilePath $BackendLog -Encoding UTF8 -Append
    $bielikVal   = if ($env:CSMW_ENABLE_BIELIK)  { $env:CSMW_ENABLE_BIELIK }  else { "0" }
    $bielikModel = if ($env:CSMW_BIELIK_MODEL)    { $env:CSMW_BIELIK_MODEL }   else { "" }
    $bielikUrl   = if ($env:CSMW_BIELIK_URL)      { $env:CSMW_BIELIK_URL }     else { "" }
    $cmd = @"
`$env:CSM_BASE_DIR = '$Root'
`$env:CSMW_ENABLE_BIELIK = '$bielikVal'
if ('$bielikModel') { `$env:CSMW_BIELIK_MODEL = '$bielikModel' }
if ('$bielikUrl')   { `$env:CSMW_BIELIK_URL   = '$bielikUrl' }
Set-Location '$ServerDir'
& '$PythonExe' -m uvicorn api:app --host 127.0.0.1 --port 8787 *>> '$BackendLog'
"@
    $proc = Start-Process powershell -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd) -WindowStyle Hidden -PassThru
    Write-ProcessId -Path $BackendPidFile -ProcessId $proc.Id
    Write-Host "Uruchamiam backend anonimizatora..." -ForegroundColor Yellow
    if (-not (Wait-HttpReady -Url "http://127.0.0.1:8787/health" -TimeoutSeconds 25 -Label "Backend CSM")) {
        Write-Host "Backend nie jest gotowy. Log backendu: $BackendLog" -ForegroundColor Red
        return $false
    }
    if (-not (Test-LocalAuth)) {
        Write-Host "Backend odpowiada, ale autoryzacja tokenem nie dziala. Nie otwieraj jeszcze Worda." -ForegroundColor Red
        return $false
    }
    return $true
}

function Start-AddinServer {
    Ensure-LogDirs
    if (Test-PortOpen 3000) {
        Stop-PortProcesses 3000
        Start-Sleep -Milliseconds 800
    }
    $certScript = Join-Path $ToolsDir "ensure-localhost-cert.ps1"
    if (-not (Test-Path -LiteralPath $certScript)) {
        Write-Host "BLAD: brak skryptu certyfikatu localhost: $certScript" -ForegroundColor Red
        return $false
    }
    # Always run the certificate verifier. Some failed installations leave
    # localhost.crt/key on disk but do not add the certificate to the user's
    # trusted root store, which makes Word/WebView block the add-in content.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $certScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "BLAD: nie udalo sie przygotowac zaufanego certyfikatu localhost." -ForegroundColor Red
        return $false
    }
    if (-not (Test-Path -LiteralPath $CertFile) -or -not (Test-Path -LiteralPath $KeyFile)) {
        Write-Host "BLAD: nadal brak certyfikatu localhost po probie utworzenia." -ForegroundColor Red
        Write-Host "Uruchom CSM -> NAPRAW albo tools\ensure-localhost-cert.ps1." -ForegroundColor Yellow
        return $false
    }
    if (-not (Test-AddinFilesReady)) { return $false }
    if (-not (Test-Path -LiteralPath $AddinStaticServer)) {
        Write-Host "BLAD: brak wbudowanego serwera HTTPS dodatku: $AddinStaticServer" -ForegroundColor Red
        return $false
    }
    "[$((Get-Date).ToString('s'))] START Python addin HTTPS server" | Out-File -FilePath $AddinLog -Encoding UTF8 -Append
    $cmd = @"
`$env:PYTHONUNBUFFERED = '1'
Set-Location '$Root'
& '$PythonExe' '$AddinStaticServer' --root '$AddinDir' --cert '$CertFile' --key '$KeyFile' --host 'all-localhost' --port 3000 *>> '$AddinLog'
"@
    $proc = Start-Process powershell -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $cmd) -WindowStyle Hidden -PassThru
    Write-ProcessId -Path $AddinPidFile -ProcessId $proc.Id
    Write-Host "Uruchamiam serwer dodatku Word na https://localhost:3000..." -ForegroundColor Yellow
    if (Wait-HttpReady -Url "https://localhost:3000/csm-token.js" -TimeoutSeconds 30 -Label "Serwer dodatku Word" -IgnoreCertificateErrors) {
        return $true
    }
    # Fallback for Windows PowerShell 5.1/self-signed-certificate edge cases:
    # if the port is listening and csm-token.js exists on disk, the server is
    # probably usable by Word/WebView even if Invoke-WebRequest could not verify
    # localhost TLS in this console process.
    if ((Wait-TcpReady -Port 3000 -TimeoutSeconds 3 -Label "Serwer dodatku Word") -and (Test-Path -LiteralPath $AddinTokenFile)) {
        Write-Host "Serwer dodatku Word dziala na porcie 3000, ale test HTTPS w PowerShell nie potwierdzil certyfikatu. Otworz koniecznie: https://localhost:3000/taskpane.html" -ForegroundColor Yellow
        return $true
    }
    Write-Host "Serwer dodatku Word nie jest gotowy. Log serwera: $AddinLog" -ForegroundColor Red
    Write-LogTail -Path $AddinLog -Lines 80
    return $false
}

if (-not (Test-Path $LicenseAccepted)) {
    throw "Nie zaakceptowano licencji. Uruchom najpierw setup-once.cmd i zaakceptuj warunki licencji."
}
# Start Ollama in background so optional Bielik review can be selected in the UI.
Ensure-OllamaRunning
# Always regenerate and synchronize the local token before starting or reusing the backend.
# The backend reads the token file on each request, so this also fixes stale token files after updates.
Prepare-ApiToken
$backendReady = Start-Backend
$addinReady = Start-AddinServer

Start-Sleep -Seconds 2

Write-Host ""
if ($backendReady -and $addinReady) {
    Write-Host "CSM jest uruchomiony i gotowy do pracy." -ForegroundColor Cyan
    Write-Host "Backend: http://127.0.0.1:8787/health"
    Write-Host "Dodatek: https://localhost:3000/taskpane.html"
} else {
    Write-Host "CSM NIE jest jeszcze gotowy do pracy." -ForegroundColor Red
    Write-Host "Nie otwieraj Worda do pracy z CSM, dopoki backend i serwer dodatku nie odpowiadaja." -ForegroundColor Yellow
    Write-Host "Sprobuj: CSM -> STOP, potem CSM -> START. Sprawdz tez w przegladarce: https://localhost:3000/taskpane.html" -ForegroundColor Yellow
    Write-Host $SupportHint -ForegroundColor Yellow
    if (-not $NonInteractive) {
        Read-Host "Nacisnij Enter, aby zamknac to okno"
    }
    exit 1
}
Write-Host ""
if ($NoOpenWord) {
    Write-Host "CSM dziala w tle. Word nie zostal automatycznie otwarty, bo uruchomiono tryb pracy w tle." -ForegroundColor Cyan
} else {
    Write-Host "Teraz otworz Worda. Dodatek powinien byc dostepny tam, gdzie dodales go poprzednio." -ForegroundColor Cyan

    try {
        Start-Process winword
    } catch {
        Write-Host "Nie udalo sie automatycznie otworzyc Worda. Otworz go recznie." -ForegroundColor Yellow
    }
}
