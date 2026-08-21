param([string]$InstallDir = "C:\CSM")
$ErrorActionPreference = "Continue"
$Root = $InstallDir
$ServerDir = Join-Path $Root "server"
$VenvPython = Join-Path $ServerDir ".venv\Scripts\python.exe"
$AddinDir = Join-Path $Root "addin"
$RuntimeDir = Join-Path $Root "runtime"
$LogsDir = Join-Path $Root "logs"
$LicenseAccepted = Join-Path $Root ".license-accepted"
$VersionJson = Join-Path $Root "VERSION.json"
$DiagFile = Join-Path $env:TEMP ("CSM-diagnostic-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".txt")

function Out-Line([string]$Text = "") {
    Write-Host $Text
    try { Add-Content -Path $DiagFile -Value $Text -Encoding UTF8 } catch {}
}

function Section([string]$Title) {
    Out-Line ""
    Out-Line "==== $Title ===="
}

function Run-Capture([string]$Label, [scriptblock]$Block) {
    Section $Label
    try { & $Block 2>&1 | ForEach-Object { Out-Line ([string]$_) } }
    catch { Out-Line ("ERROR: " + $_.Exception.Message) }
}

Out-Line "CSM diagnostic"
Out-Line "Time: $(Get-Date -Format o)"
Out-Line "User: $([Security.Principal.WindowsIdentity]::GetCurrent().Name)"
Out-Line "InstallDir: $InstallDir"
Out-Line "Diagnostic file: $DiagFile"

Section "Wersja CSM"
try {
    if (Test-Path -LiteralPath $VersionJson) {
        $ver = Get-Content -LiteralPath $VersionJson -Raw -ErrorAction SilentlyContinue | ConvertFrom-Json -ErrorAction SilentlyContinue
        Out-Line "version=$($ver.version)  build=$($ver.build)  label=$($ver.label)"
    } else { Out-Line "VERSION.json brak: $VersionJson" }
} catch { Out-Line "Blad odczytu VERSION.json: $($_.Exception.Message)" }

Section "Licencja i pliki CSM"
$licStatus = if (Test-Path -LiteralPath $LicenseAccepted) {
    "ZAAKCEPTOWANA: " + (Get-Content -LiteralPath $LicenseAccepted -ErrorAction SilentlyContinue)
} else { "BRAK — licencja nie zostala zaakceptowana" }
Out-Line ".license-accepted: $licStatus"
foreach ($path in @($Root, $ServerDir, $VenvPython, $AddinDir, (Join-Path $AddinDir "taskpane.html"), (Join-Path $AddinDir "manifest.xml"))) {
    $status = if (Test-Path -LiteralPath $path) { "OK     " } else { "BRAK   " }
    Out-Line ($status + $path)
}

Section "Skrypty CSM — wersje i hashe"
foreach ($script in @("install-csm.ps1", "setup-once.ps1", "start-claude-safe-mode.ps1", "diagnose-csm.ps1")) {
    $sp = Join-Path $Root "tools\$script"
    if (Test-Path -LiteralPath $sp) {
        try {
            $hash = (Get-FileHash -LiteralPath $sp -Algorithm SHA256 -ErrorAction SilentlyContinue).Hash
            $firstLine = (Get-Content -LiteralPath $sp -TotalCount 3 -ErrorAction SilentlyContinue) -join " | "
            Out-Line "$script  SHA256=$hash"
            Out-Line "  header: $firstLine"
        } catch { Out-Line "$script  blad: $($_.Exception.Message)" }
    } else { Out-Line "BRAK   $sp" }
}

Section "Stan polinstalacji (half-installed check)"
$venvOk = Test-Path -LiteralPath $VenvPython
$catalogReg = $false
try {
    $base = "HKCU:\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs"
    if (Test-Path $base) {
        $catalogReg = @(Get-ChildItem $base | ForEach-Object {
            (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).Url
        } | Where-Object { $_ -like "*ClaudeSafeModeAddin*" -or $_ -like "*CSMAddin*" }).Count -gt 0
    }
} catch {}
$licOk = Test-Path -LiteralPath $LicenseAccepted
Out-Line ".venv ok=$venvOk  Word-catalog-registered=$catalogReg  license-accepted=$licOk"
if ($catalogReg -and -not $venvOk) {
    Out-Line "ROOT_CAUSE_LIKELY=half-installed: Word widzi dodatek, ale backend nie istnieje (.venv brak). Uruchom CSM -> NAPRAW lub reinstaluj."
} elseif (-not $licOk -and -not $venvOk) {
    Out-Line "ROOT_CAUSE_LIKELY=licencja nie zaakceptowana + brak .venv: setup-once.ps1 nie zostal uruchomiony. Uruchom instalator ponownie."
} elseif (-not $venvOk) {
    Out-Line "ROOT_CAUSE_LIKELY=brak .venv: setup-once.ps1 zakonczyl sie bledem lub Python 3.12 nie jest dostepny. Sprawdz logi setup-once."
} elseif (-not $catalogReg) {
    Out-Line "ROOT_CAUSE_LIKELY=Word nie ma wpisu TrustedCatalog: instalacja nie zostala ukonczona lub wpis zostal usuniety."
} else {
    Out-Line "ROOT_CAUSE_LIKELY=brak (infrastruktura OK — sprawdz czy procesy na portach 3000/8787 sa uruchomione)"
}

Run-Capture "Python w systemie" {
    foreach ($cmd in @("py", "python", "python3")) {
        $found = Get-Command $cmd -ErrorAction SilentlyContinue
        if ($found) {
            Write-Output "$cmd -> $($found.Source)"
            & $cmd --version 2>&1
        } else { Write-Output "$cmd -> brak" }
    }
    if (Test-Path -LiteralPath $VenvPython) {
        Write-Output "--- .venv ---"
        & $VenvPython -c "import sys,struct; print('venv=' + sys.executable); print('version=' + sys.version); print('bits=' + str(8*struct.calcsize('P')))" 2>&1
        $importResult = & $VenvPython -c "import fastapi,uvicorn,pydantic,lxml.etree; print('imports=OK')" 2>&1
        Write-Output $importResult
        if ($importResult -notmatch "imports=OK") { Write-Output "UWAGA: importy wymaganych modulow nie przechodza!" }
        Write-Output "--- pip list (top packages) ---"
        & $VenvPython -m pip list --disable-pip-version-check 2>&1 | Select-Object -First 30 | ForEach-Object { Write-Output $_ }
    } else {
        Write-Output ".venv\Scripts\python.exe BRAK — backend nie moze dzialac"
    }
}

Run-Capture "Porty i procesy" {
    foreach ($port in 3000,8787) {
        Write-Output "-- port $port --"
        try { Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Format-Table -AutoSize | Out-String }
        catch { Write-Output $_.Exception.Message }
    }
    foreach ($pidFile in @((Join-Path $RuntimeDir "addin.pid"), (Join-Path $RuntimeDir "backend.pid"))) {
        if (Test-Path -LiteralPath $pidFile) {
            $pidText = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
            Write-Output "$pidFile -> $pidText"
            if ($pidText) { Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue | Format-List | Out-String }
        } else { Write-Output "$pidFile -> brak" }
    }
}

Run-Capture "HTTP lokalne" {
    try { Invoke-WebRequest -Uri "http://127.0.0.1:8787/health" -UseBasicParsing -TimeoutSec 5 | Select-Object StatusCode,Content | Format-List | Out-String } catch { Write-Output "backend health ERROR: $($_.Exception.Message)" }
    try {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        Invoke-WebRequest -Uri "https://localhost:3000/taskpane.html" -UseBasicParsing -TimeoutSec 5 | Select-Object StatusCode,Content | Format-List | Out-String
    } catch { Write-Output "addin https ERROR: $($_.Exception.Message)" }
}

Run-Capture "Certyfikat localhost" {
    $certFile = Join-Path $env:USERPROFILE ".office-addin-dev-certs\localhost.crt"
    $keyFile = Join-Path $env:USERPROFILE ".office-addin-dev-certs\localhost.key"
    Write-Output "cert=$certFile exists=$(Test-Path -LiteralPath $certFile)"
    Write-Output "key =$keyFile exists=$(Test-Path -LiteralPath $keyFile)"
    if (Test-Path -LiteralPath $certFile) {
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($certFile)
        Write-Output "thumbprint=$($cert.Thumbprint) subject=$($cert.Subject) notAfter=$($cert.NotAfter)"
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
        try { Write-Output "trusted=$(@($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }).Count -gt 0)" }
        finally { $store.Close() }
    }
}

Run-Capture "Word TrustedCatalogs i udzial" {
    $shareManifest = "\\localhost\ClaudeSafeModeAddin\manifest.xml"
    Write-Output "$shareManifest exists=$(Test-Path -LiteralPath $shareManifest)"
    $base = "HKCU:\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs"
    if (Test-Path $base) {
        Get-ChildItem $base | ForEach-Object { Get-ItemProperty $_.PSPath | Select-Object PSChildName,Id,Url,Flags | Format-List | Out-String }
    } else { Write-Output "TrustedCatalogs key missing" }
}

Run-Capture "Autostart" {
    Get-ScheduledTask -TaskName "CSM AutoStart" -ErrorAction SilentlyContinue | Format-List | Out-String
}

Section "Ostatnie logi"
foreach ($log in @(
    (Join-Path $LogsDir "backend-8787.log"),
    (Join-Path $LogsDir "addin-3000.log"),
    (Join-Path $env:TEMP "CSM-install.log"),
    (Join-Path $env:TEMP "CSM-setup-once.log")
)) {
    Out-Line "--- $log ---"
    if (Test-Path -LiteralPath $log) { Get-Content -LiteralPath $log -Tail 200 -ErrorAction SilentlyContinue | ForEach-Object { Out-Line $_ } }
    else { Out-Line "brak" }
}

Out-Line ""
Out-Line "Gotowe. Plik diagnostyczny: $DiagFile"
Out-Line "Jesli cos nie dziala, napisz na csm@kancelariakantorowski.pl - pomoze nam to rozwiazac Twoj problem."
try { Start-Process notepad.exe $DiagFile } catch {}
