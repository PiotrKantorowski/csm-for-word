<#
CSM v1.6 installer.
User-facing entrypoint is ZAINSTALUJ_CSM.cmd.

Important implementation detail:
Administrative work (copying to C:\CSM and creating the SMB share) is separated
from user-profile work (HKCU TrustedCatalogs, Office cache, desktop shortcut).
This avoids installing the Word catalog and shortcut into the administrator
profile when UAC asks for elevation.
#>

param(
    [string]$InstallDir = "C:\CSM",
    [switch]$SkipDependencies,
    [switch]$NoStart,
    [switch]$NoAutostart,
    [switch]$ElevatedPhase,
    [switch]$FromInstaller,
    [switch]$AcceptLicense,
    [string]$OriginalSourceRoot = "",
    [string]$OriginalUserSid = "",
    [string]$OriginalDesktop = "",
    [string]$OriginalLocalAppData = "",
    # Parametry VPS (opcjonalne — gdy puste = tryb lokalny)
    [ValidateSet('', 'hetzner', 'ionos')]
    [string]$VpsProvider = "",
    [string]$VpsApiKey = "",
    [string]$VpsDomain = "",
    [string]$VpsRegion = "",
    # Model Bielik (dla VPS: instalowany na serwerze; lokalnie: pobierany przez Ollama)
    [string]$BielikModel = "hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M",
    # Silnik embeddingów dla VPS
    [ValidateSet('ollama', 'voyage')]
    [string]$EmbeddingProvider = "ollama",
    [string]$VoyageApiKey = ""
)

$ErrorActionPreference = "Stop"
$script:psExe = if (Get-Command pwsh -ErrorAction SilentlyContinue) { (Get-Command pwsh).Source } else { "powershell.exe" }
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SourceRoot = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
if ($OriginalSourceRoot) { $SourceRoot = $OriginalSourceRoot }
$ToolsDir = Join-Path $InstallDir "tools"
$ShareName = "ClaudeSafeModeAddin"
$CatalogUrl = "\\localhost\$ShareName\"
$LogPath = Join-Path $env:TEMP "CSM-install.log"
$script:ShareReady = $true
$SupportEmail = "csm@kancelariakantorowski.pl"
$SupportHint = "Jesli cos nie dziala, napisz na $SupportEmail - pomoze nam to rozwiazac Twoj problem."

function Initialize-InstallLog {
    try {
        $header = @(
            "CSM install log",
            "Started: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
            "User: $([Security.Principal.WindowsIdentity]::GetCurrent().Name)",
            "Script: $PSCommandPath",
            ""
        )
        Set-Content -Path $LogPath -Value $header -Encoding UTF8
    } catch { }
}

function Write-Step {
    param([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::White)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host $Message -ForegroundColor $Color
    try { Add-Content -Path $LogPath -Value "[$stamp] $Message" -Encoding UTF8 } catch { }
}

function Write-SupportHint {
    Write-Step $SupportHint Yellow
}

$script:CsmInstallTrapActive = $true
trap {
    try {
        Write-Step ""
        Write-Step "[CSM] Instalacja zakonczyla sie bledem." Red
        Write-SupportHint
        Write-Step "Log instalacji: $LogPath" Yellow
    } catch { }
    exit 1
}

function Get-CurrentUserSid {
    return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Stop-Word {
    Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
}

function Clear-OfficeCache {
    param([string]$LocalAppData = $env:LOCALAPPDATA)
    if (-not $LocalAppData) { return }
    $officeBase = Join-Path $LocalAppData "Microsoft\Office\16.0"
    foreach ($sub in @("Wef", "WebServiceCache", "OfficeFileCache")) {
        $path = Join-Path $officeBase $sub
        if (Test-Path -LiteralPath $path) {
            try {
                Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
                Write-Step "Wyczyszczono cache: $path" Green
            } catch {
                Write-Step "Nie udalo sie w pelni wyczyscic: $path" Yellow
            }
        }
    }
}


function Invoke-NativeLogged {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [string]$Description = $FilePath
    )

    # Do not execute native tools with stderr redirected through the PowerShell
    # pipeline while $ErrorActionPreference = Stop. On some localized Windows
    # builds, harmless net.exe stderr such as "Ten zasob udostepniony nie
    # istnieje" is promoted to a terminating ErrorRecord. That was blocking the
    # whole installer before the user-profile phase could create the CSM icon.
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    $outputLines = @()
    $code = 9999
    try {
        $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $code = $proc.ExitCode
        if (Test-Path -LiteralPath $stdoutFile) {
            $outputLines += Get-Content -LiteralPath $stdoutFile -Encoding OEM -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $stderrFile) {
            $outputLines += Get-Content -LiteralPath $stderrFile -Encoding OEM -ErrorAction SilentlyContinue
        }
    } catch {
        $outputLines += $_.Exception.Message
    } finally {
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }

    if ($outputLines) {
        foreach ($line in $outputLines) {
            if ($line) { Write-Step "${Description}: $line" DarkGray }
        }
    }
    return @{ Code = $code; Output = ($outputLines -join "`n") }
}

function Invoke-NativeTimed {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [string]$Description = $FilePath,
        [int]$TimeoutSeconds = 15
    )

    # Native tools such as icacls can take a very long time when C:\CSM already
    # contains old sessions/backups. The installer must not hang before the
    # user-profile phase creates the CSM desktop icon. This helper captures
    # output, applies a hard timeout and returns a non-fatal result to callers.
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    $outputLines = @()
    $code = 9998
    $timedOut = $false
    try {
        $proc = Start-Process -FilePath $FilePath -ArgumentList $Arguments -NoNewWindow -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        $timeoutMs = [int]($TimeoutSeconds * 1000)
        if (-not $proc.WaitForExit($timeoutMs)) {
            $timedOut = $true
            try { $proc.Kill() } catch { }
            try { $proc.WaitForExit(2000) | Out-Null } catch { }
            $code = -999
            $outputLines += "TIMEOUT after $TimeoutSeconds seconds"
        } else {
            # Flush async I/O and populate ExitCode — required on PS5.1/.NET Framework
            $proc.WaitForExit()
            $code = if ($null -ne $proc.ExitCode) { [int]$proc.ExitCode } else { 0 }
        }
        if (Test-Path -LiteralPath $stdoutFile) {
            $outputLines += Get-Content -LiteralPath $stdoutFile -Encoding OEM -ErrorAction SilentlyContinue
        }
        if (Test-Path -LiteralPath $stderrFile) {
            $outputLines += Get-Content -LiteralPath $stderrFile -Encoding OEM -ErrorAction SilentlyContinue
        }
    } catch {
        $outputLines += $_.Exception.Message
    } finally {
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }

    if ($outputLines) {
        foreach ($line in $outputLines) {
            if ($line) { Write-Step "${Description}: $line" DarkGray }
        }
    }
    return @{ Code = $code; Output = ($outputLines -join "`n"); TimedOut = $timedOut }
}

function Quote-ChildArgument([string]$Argument) {
    if ($null -eq $Argument) { return '""' }
    $arg = [string]$Argument
    if ($arg -match '[\s"]') { return '"' + $arg.Replace('"', '\"') + '"' }
    return $arg
}

function Invoke-ChildPowerShellLoggedTimed {
    param(
        [Parameter(Mandatory=$true)][string]$ScriptPath,
        [string[]]$Arguments = @(),
        [string]$Description = "PowerShell script",
        [int]$TimeoutSeconds = 900
    )
    $stdoutFile = [System.IO.Path]::GetTempFileName()
    $stderrFile = [System.IO.Path]::GetTempFileName()
    try {
        $allArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $ScriptPath) + $Arguments
        $argumentLine = (($allArgs | ForEach-Object { Quote-ChildArgument ([string]$_) }) -join " ")
        Write-Step "Uruchamiam: $Description" Yellow
        $proc = Start-Process -FilePath $script:psExe -ArgumentList $argumentLine -NoNewWindow -PassThru -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile
        if (-not $proc.WaitForExit($TimeoutSeconds * 1000)) {
            try { $proc.Kill() } catch { }
            try { $proc.WaitForExit(3000) | Out-Null } catch { }
            Write-Step "$Description przekroczyl limit czasu $TimeoutSeconds s." Red
            return @{ Code = -999; TimedOut = $true; Output = "timeout" }
        }
        # Flush async I/O and populate ExitCode — required on PS5.1/.NET Framework
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
            if ($line -and ([string]$line).Trim()) { Write-Step "${Description}: $line" DarkGray }
        }
        return @{ Code = $exitCode; TimedOut = $false; Output = ($lines -join "`n") }
    } finally {
        Remove-Item -LiteralPath $stdoutFile, $stderrFile -Force -ErrorAction SilentlyContinue
    }
}

function Test-MissingShareMessage {
    param([string]$Message)
    if (-not $Message) { return $false }
    return (
        $Message -match "(?i)does not exist" -or
        $Message -match "(?i)was not found" -or
        $Message -match "(?i)not found" -or
        $Message -match "2310" -or
        $Message -match "nie istnieje" -or
        $Message -match "nie znaleziono"
    )
}

function Ensure-LanmanServer {
    try {
        $svc = Get-Service -Name LanmanServer -ErrorAction Stop
        if ($svc.Status -ne 'Running') {
            Write-Step "Uruchamiam usluge udostepniania plikow Windows (LanmanServer)..." Yellow
            try { Set-Service -Name LanmanServer -StartupType Manual -ErrorAction SilentlyContinue } catch { }
            Start-Service -Name LanmanServer -ErrorAction Stop
            $svc.WaitForStatus('Running', [TimeSpan]::FromSeconds(15))
        }
        Write-Step "Usluga LanmanServer dziala." Green
        return $true
    } catch {
        Write-Step "OSTRZEZENIE: nie udalo sie uruchomic uslugi LanmanServer wymaganej do udzialu Worda: $($_.Exception.Message)" Yellow
        Write-Step "Instalacja nie zostanie przerwana, ale Word moze nie zobaczyc dodatku do czasu naprawy udostepniania plikow Windows." Yellow
        return $false
    }
}

function Test-AddinShare {
    $manifestUnc = "\\localhost\$ShareName\manifest.xml"
    try {
        if (Test-Path -LiteralPath $manifestUnc) {
            Write-Step "Zweryfikowano dostep do manifestu przez: $manifestUnc" Green
            return $true
        }
    } catch {
        Write-Step "Nie udalo sie sprawdzic manifestu przez UNC: $($_.Exception.Message)" Yellow
    }
    return $false
}

function Wait-AddinShare {
    param([int]$Attempts = 12, [int]$DelayMilliseconds = 750)
    for ($i = 1; $i -le $Attempts; $i++) {
        if (Test-AddinShare) { return $true }
        if ($i -lt $Attempts) {
            Write-Step "Czekam na dostepnosc udzialu Worda ($i/$Attempts)..." DarkGray
            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }
    return $false
}

function Copy-CSMFiles {
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    $source = (Resolve-Path -LiteralPath $SourceRoot).Path.TrimEnd('\')
    $target = (Resolve-Path -LiteralPath $InstallDir).Path.TrimEnd('\')
    if ($source -ieq $target) {
        Write-Step "Instalator uruchomiony z katalogu docelowego: $InstallDir" Cyan
        return
    }
    Write-Step "Kopiuje pliki CSM do $InstallDir..." Yellow
    $excludeDirs = @(".git", ".pytest_cache", "__pycache__", "node_modules", ".venv")
    Get-ChildItem -LiteralPath $SourceRoot -Force | ForEach-Object {
        if ($excludeDirs -contains $_.Name) { return }
        $dest = Join-Path $InstallDir $_.Name
        Copy-Item -LiteralPath $_.FullName -Destination $dest -Recurse -Force
    }
}

function Grant-PathAccessFast {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][string]$Grant,
        [string]$Description = "icacls",
        [int]$TimeoutSeconds = 12
    )
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $result = Invoke-NativeTimed -FilePath "icacls.exe" -Arguments @($Path, "/inheritance:e", "/grant", $Grant, "/C") -Description $Description -TimeoutSeconds $TimeoutSeconds
    if ($result.TimedOut) {
        Write-Step "OSTRZEZENIE: $Description przekroczyl limit czasu. Instalacja idzie dalej; w razie problemu uzyj NAPRAW." Yellow
    } elseif ($result.Code -ne 0) {
        Write-Step "OSTRZEZENIE: $Description zwrocil kod $($result.Code). Instalacja idzie dalej." Yellow
    }
}

function Grant-InstallAccess {
    if (-not $OriginalUserSid) { return }
    Write-Step "Nadaje podstawowe uprawnienia do $InstallDir dla biezacego uzytkownika..." Yellow
    Write-Step "Pomijam wolne rekurencyjne icacls /T, aby instalator nie zawieszal sie na starych sesjach/backups." DarkGray
    $grant = "*${OriginalUserSid}:(OI)(CI)M"
    foreach ($rel in @("", "runtime", "sessions", "backups", "addin", "server\audit")) {
        $path = if ($rel) { Join-Path $InstallDir $rel } else { $InstallDir }
        try {
            if (-not (Test-Path -LiteralPath $path)) {
                New-Item -ItemType Directory -Force -Path $path | Out-Null
            }
            Grant-PathAccessFast -Path $path -Grant $grant -Description "icacls user modify $path" -TimeoutSeconds 12
        } catch {
            Write-Step "OSTRZEZENIE: nie udalo sie ustawic uprawnien dla ${path}: $($_.Exception.Message)" Yellow
        }
    }
}

function Resolve-AccountName {
    param([string]$Sid)
    if (-not $Sid) { return $null }
    try {
        $sidObj = New-Object System.Security.Principal.SecurityIdentifier($Sid)
        return $sidObj.Translate([System.Security.Principal.NTAccount]).Value
    } catch {
        Write-Step "Nie udalo sie przetlumaczyc SID $Sid na nazwe konta: $($_.Exception.Message)" Yellow
        return $null
    }
}

function Grant-AddinReadAccess {
    param([string]$AddinDir)
    $sidGrants = @()
    if ($OriginalUserSid) { $sidGrants += "*${OriginalUserSid}:(OI)(CI)RX" }
    $sidGrants += "*S-1-1-0:(OI)(CI)RX" # Everyone / Wszyscy, niezaleznie od jezyka Windows.
    foreach ($grant in ($sidGrants | Select-Object -Unique)) {
        try {
            Grant-PathAccessFast -Path $AddinDir -Grant $grant -Description "icacls addin read $grant" -TimeoutSeconds 10
        } catch {
            Write-Step "Ostrzezenie: nie udalo sie nadac NTFS $grant dla ${AddinDir}: $($_.Exception.Message)" Yellow
        }
    }
}

function Remove-ExistingShare {
    $checkedWithSmbShare = $false
    if (Get-Command Get-SmbShare -ErrorAction SilentlyContinue) {
        $checkedWithSmbShare = $true
        $existing = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
        if ($existing) {
            try {
                Remove-SmbShare -Name $ShareName -Force -ErrorAction Stop
                Write-Step "Usunieto poprzedni udzial $ShareName przez Remove-SmbShare." Yellow
                return
            } catch {
                Write-Step "Nie udalo sie usunac udzialu przez Remove-SmbShare: $($_.Exception.Message)" Yellow
                Write-Step "Kontynuuje probe usuniecia przez net share." DarkGray
            }
        } else {
            Write-Step "Brak poprzedniego udzialu $ShareName do usuniecia." DarkGray
            return
        }
    }

    $result = Invoke-NativeLogged -FilePath "net.exe" -Arguments @("share", $ShareName, "/delete", "/y") -Description "net share delete"
    if ($result.Code -eq 0) {
        Write-Step "Usunieto poprzedni udzial $ShareName przez net share." Yellow
    } elseif (Test-MissingShareMessage -Message $result.Output) {
        Write-Step "Brak poprzedniego udzialu $ShareName do usuniecia przez net share." DarkGray
    } elseif ($checkedWithSmbShare) {
        Write-Step "Nie mozna usunac poprzedniego udzialu przez net share. Kod: $($result.Code). Kontynuuje instalacje, bo udzial nie byl widoczny przez Get-SmbShare." Yellow
    } else {
        Write-Step "Nie mozna potwierdzic usuniecia poprzedniego udzialu przez net share. Kod: $($result.Code). Kontynuuje instalacje." Yellow
    }
}

function Ensure-Share {
    $addinDir = Join-Path $InstallDir "addin"
    if (-not (Test-Path -LiteralPath (Join-Path $addinDir "manifest.xml"))) {
        throw "Nie znaleziono manifest.xml w $addinDir"
    }

    if (-not (Ensure-LanmanServer)) {
        $script:ShareReady = $false
        return $false
    }
    Grant-AddinReadAccess -AddinDir $addinDir
    try {
        Remove-ExistingShare
    } catch {
        Write-Step "OSTRZEZENIE: czyszczenie poprzedniego udzialu $ShareName nie powiodlo sie, ale instalacja nie zostanie przerwana: $($_.Exception.Message)" Yellow
    }

    $originalAccount = Resolve-AccountName -Sid $OriginalUserSid
    $everyoneAccount = Resolve-AccountName -Sid "S-1-1-0"
    $usersAccount = Resolve-AccountName -Sid "S-1-5-32-545"
    $shareAccounts = @($originalAccount, $everyoneAccount, $usersAccount) | Where-Object { $_ } | Select-Object -Unique

    $created = $false
    $lastError = $null

    if (Get-Command New-SmbShare -ErrorAction SilentlyContinue) {
        foreach ($accounts in @($shareAccounts, @($originalAccount), @($everyoneAccount), @($usersAccount))) {
            $accounts = @($accounts | Where-Object { $_ } | Select-Object -Unique)
            if (-not $accounts -or $accounts.Count -eq 0) { continue }
            try {
                New-SmbShare -Name $ShareName -Path $addinDir -ReadAccess $accounts -ErrorAction Stop | Out-Null
                $created = $true
                Write-Step "Utworzono udzial SMB przez New-SmbShare dla: $($accounts -join ', ')" Green
                break
            } catch {
                $lastError = $_.Exception.Message
                Write-Step "New-SmbShare nie powiodl sie dla '$($accounts -join ', ')': $lastError" Yellow
            }
        }
    }

    if (-not $created) {
        $candidateAccounts = @($everyoneAccount, $usersAccount, $originalAccount, "Everyone") | Where-Object { $_ } | Select-Object -Unique
        foreach ($grantAccount in $candidateAccounts) {
            $shareArg = "$ShareName=$addinDir"
            $grantArg = "/GRANT:$grantAccount,READ"
            $result = Invoke-NativeLogged -FilePath "net.exe" -Arguments @("share", $shareArg, $grantArg) -Description "net share create"
            if ($result.Code -eq 0) {
                $created = $true
                Write-Step "Utworzono udzial SMB przez net share dla: $grantAccount" Green
                break
            }
            $lastError = "net share zwrocil kod $($result.Code) dla konta $grantAccount. Wyjscie: $($result.Output)"
            Write-Step $lastError Yellow
        }
    }

    if (-not $created) {
        Write-Step "OSTRZEZENIE: nie udalo sie utworzyc udzialu $CatalogUrl. Ostatni blad: $lastError" Yellow
        Write-Step "Instalacja bedzie kontynuowana, aby utworzyc skrot CSM i wpis Worda. Uzyj NAPRAW po restarcie Windows albo przeslij log instalacji." Yellow
        $script:ShareReady = $false
        return $false
    }

    if (-not (Wait-AddinShare)) {
        Write-Step "OSTRZEZENIE: udzial $CatalogUrl zostal utworzony, ale Windows nie udostepnil jeszcze manifest.xml przez UNC." Yellow
        Write-Step "Nie przerywam instalacji. Word moze zobaczyc dodatek po odswiezeniu folderu udostepnionego albo po uzyciu NAPRAW." Yellow
        $script:ShareReady = $false
        return $false
    }

    Write-Step "Utworzono udzial $CatalogUrl -> $addinDir" Green
    return $true
}

function Add-TrustedCatalogRegistry {
    $base = "HKCU:\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs"
    New-Item -Path $base -Force | Out-Null
    Get-ChildItem -Path $base -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $url = (Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue).Url
            if ($url -like "*ClaudeSafeModeAddin*" -or $url -like "*CSMAddin*") {
                Remove-Item -Path $_.PSPath -Recurse -Force -ErrorAction SilentlyContinue
            }
        } catch { }
    }
    $keyName = "CSM-Local-" + ([Guid]::NewGuid().ToString("N"))
    $key = Join-Path $base $keyName
    New-Item -Path $key -Force | Out-Null
    New-ItemProperty -Path $key -Name "Id" -Value $CatalogUrl -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $key -Name "Url" -Value $CatalogUrl -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $key -Name "Flags" -Value 3 -PropertyType DWord -Force | Out-Null
    Write-Step "Dodano zaufany katalog Word w profilu uzytkownika: $CatalogUrl" Green
}

function Run-SetupOnce {
    if ($SkipDependencies) { return }
    $setup = Join-Path $ToolsDir "setup-once.ps1"
    if (Test-Path -LiteralPath $setup) {
        # Always pass -FromInstaller and -AcceptLicense when called from any installer
        # context — never rely on conditional heuristics like $OriginalSourceRoot.
        # This prevents Read-Host from being called in non-interactive hidden contexts.
        #
        # Call setup-once.ps1 directly (without -RedirectStandard*) so output streams
        # to console in real time. Users would otherwise see a frozen window for the
        # entire duration of Python/pip installation (can be 5-20 min on first run).
        # setup-once.ps1 writes its own timestamped log to %TEMP%\CSM-setup-once.log
        # and has per-operation timeouts internally, so the outer timeout is not needed.
        Write-Step "Konfiguracja jednorazowa (pierwsze uruchomienie: instalacja Python/pip moze potrwac kilka minut)..." Yellow
        $setupArgs = @("-SkipShareHint", "-FromInstaller", "-AcceptLicense")
        if ($BielikModel -ne "") { $setupArgs += @("-BielikModel", $BielikModel) }
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $setup @setupArgs
        $setupCode = $LASTEXITCODE
        if ($setupCode -ne 0) {
            Write-SupportHint
            throw "setup-once.ps1 zakonczyl sie bledem (kod $setupCode). Sprawdz log: %TEMP%\CSM-setup-once.log"
        }
    }
}

function Assert-VenvReady {
    # Hard fail before registering the Word catalog — a visible add-in that cannot
    # connect to the backend is worse (and harder to diagnose) than a clean abort.
    $venvPython = Join-Path $InstallDir "server\.venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $venvPython)) {
        throw "BLAD RC17: .venv\Scripts\python.exe nie istnieje po setup-once.ps1. Instalacja przerwana przed rejestracją dodatku Word, zeby uniknac stanu polinstalacji. Sprawdz: $LogPath oraz %TEMP%\CSM-setup-once.log"
    }
    try {
        & $venvPython -c "import fastapi, uvicorn, pydantic, lxml.etree" 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "Importy Python nie przechodza w .venv."
        }
        Write-Step ".venv zweryfikowane — fastapi, uvicorn, pydantic, lxml.etree OK." Green
    } catch {
        throw "BLAD RC17: .venv istnieje, ale importy wymaganych modulow Python nie przechodza: $($_.Exception.Message). Instalacja przerwana przed rejestracją dodatku Word."
    }
}

# start flags: -NoOpenWord -NonInteractive
# legacy contract equivalent: & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $start -NoOpenWord -NonInteractive
function Start-CSM {
    if ($NoStart) { return }
    $start = Join-Path $ToolsDir "start-claude-safe-mode.ps1"
    if (Test-Path -LiteralPath $start) {
        Write-Step "Uruchamiam CSM i sprawdzam, czy localhost:3000 jest gotowy..." Yellow
        $startResult = Invoke-ChildPowerShellLoggedTimed -ScriptPath $start -Arguments @("-NoOpenWord", "-NonInteractive") -Description "start-claude-safe-mode.ps1" -TimeoutSeconds 120
        if ($startResult.Code -ne 0) {
            Write-Step "OSTRZEZENIE: CSM nie wystartowal poprawnie po instalacji. Otworz ikone CSM -> DIAGNOZA albo NAPRAW." Yellow
            Write-SupportHint
            Write-Step "Sprawdz logi: $InstallDir\logs\addin-3000.log oraz $InstallDir\logs\backend-8787.log" Yellow
            Write-SupportHint
            $diag = Join-Path $ToolsDir "diagnose-csm.ps1"
            if (Test-Path -LiteralPath $diag) {
                Write-Step "Uruchamiam szybka diagnostyke CSM..." Yellow
                & $script:psExe -NoProfile -ExecutionPolicy Bypass -File $diag -InstallDir $InstallDir
            }
        } else {
            Write-Step "CSM wystartowal poprawnie. Panel powinien odpowiadac pod: https://localhost:3000/taskpane.html" Green
        }
    }
}

function Enable-Autostart {
    if ($NoAutostart) { return }
    $autostart = Join-Path $ToolsDir "register-autostart.ps1"
    if (Test-Path -LiteralPath $autostart) {
        try {
            & $script:psExe -NoProfile -ExecutionPolicy Bypass -File $autostart -InstallDir $InstallDir
            if ($LASTEXITCODE -ne 0) {
                throw "register-autostart.ps1 zakonczyl sie bledem."
            }
            Write-Step "Wlaczono autostart CSM przy logowaniu uzytkownika." Green
        } catch {
            Write-Step "OSTRZEZENIE: nie udalo sie wlaczyc autostartu CSM: $($_.Exception.Message)" Yellow
            Write-Step "CSM nadal mozna uruchomic recznie z ikony na pulpicie." Yellow
            Write-SupportHint
        }
    }
}

function Invoke-ElevatedPhase {
    Write-Step "Instalator wymaga uprawnien administratora tylko do skopiowania plikow i utworzenia udzialu Worda." Yellow
    Write-Step "Po oknie UAC instalacja wroci do profilu uzytkownika i utworzy w nim skrot oraz wpis Worda." Yellow
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-InstallDir", "`"$InstallDir`"",
        "-ElevatedPhase",
        "-OriginalSourceRoot", "`"$SourceRoot`"",
        "-OriginalUserSid", "`"$OriginalUserSid`"",
        "-OriginalDesktop", "`"$OriginalDesktop`"",
        "-OriginalLocalAppData", "`"$OriginalLocalAppData`""
    )
    $proc = Start-Process -FilePath $script:psExe -ArgumentList $args -Verb RunAs -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-Step "Etap administratora zwrocil kod $($proc.ExitCode). Ostatnie linie logu:" Red
        try {
            Get-Content -Path $LogPath -Tail 80 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_ -ForegroundColor DarkYellow }
        } catch { }
        throw "Etap administratora zakonczyl sie bledem. Kod: $($proc.ExitCode). Log: $LogPath"
    }
}

if (-not $OriginalUserSid) { $OriginalUserSid = Get-CurrentUserSid }
if (-not $OriginalDesktop) { $OriginalDesktop = [Environment]::GetFolderPath("Desktop") }
if (-not $OriginalLocalAppData) { $OriginalLocalAppData = $env:LOCALAPPDATA }

if (-not $ElevatedPhase) { Initialize-InstallLog }
elseif (-not (Test-Path -LiteralPath $LogPath)) { Initialize-InstallLog }

Write-Step "CSM v1.0 rc19 - instalacja jednym plikiem" Cyan
Write-Step "Folder docelowy: $InstallDir" Cyan
Write-Step "Log instalacji: $LogPath" Cyan
Stop-Word

if ($ElevatedPhase) {
    try {
        if (-not (Test-Admin)) { throw "Etap administratora zostal uruchomiony bez uprawnien administratora." }
        Copy-CSMFiles
        Grant-InstallAccess
        $shareOk = Ensure-Share
        if (-not $shareOk) {
            Write-Step "Etap administratora zakonczony z ostrzezeniem dotyczacym udzialu Worda, ale bez blokowania instalacji uzytkownika." Yellow
        }
        exit 0
    } catch {
        Write-Step "BLAD etapu administratora: $($_.Exception.Message)" Red
        Write-Step "Szczegoly bledu: $($_.ScriptStackTrace)" Red
        Write-SupportHint
        exit 1
    }
}

if ($VpsProvider -eq "" -and $AcceptLicense -and -not $SkipDependencies -and -not $FromInstaller) {
    Write-Step "" White
    Write-Step "=== Model AI (Bielik) — wybierz tryb instalacji ===" Cyan
    Write-Step "  1. Lokalnie przez Ollama (domyslnie — dane nie opuszczaja komputera)" White
    Write-Step "  2. Hetzner Cloud  (Niemcy, RODO + ISO 27001, ~6-10 EUR/mies.)" White
    Write-Step "  3. IONOS Cloud    (Niemcy/Frankfurt, RODO)" White
    Write-Step "" White
    try {
        $vpsChoice = Read-Host "Wybor [1-3, Enter = lokalnie]"
    } catch { $vpsChoice = "1" }
    $providerMap = @{ "2"="hetzner"; "3"="ionos" }
    if ($providerMap.ContainsKey($vpsChoice.Trim())) {
        $VpsProvider = $providerMap[$vpsChoice.Trim()]
        Write-Step "" White
        Write-Step "Wybrany dostawca: $VpsProvider" Green
        try { $VpsApiKey = Read-Host "Klucz API $VpsProvider (wygeneruj w panelu dostawcy)" } catch { $VpsApiKey = "" }
        try { $VpsDomain = Read-Host "Domena dla CSM (np. csm.kancelaria.pl)" } catch { $VpsDomain = "" }
        $defaultRegion = if ($VpsProvider -eq "hetzner") { "fsn1" } elseif ($VpsProvider -eq "ionos") { "de" } else { "" }
        try {
            $regionPrompt = if ($defaultRegion) { "Region [$defaultRegion, Enter = domyslny]" } else { "Region (opcjonalnie, Enter = domyslny)" }
            $r = Read-Host $regionPrompt
            $VpsRegion = if ($r.Trim()) { $r.Trim() } else { $defaultRegion }
        } catch { $VpsRegion = $defaultRegion }
        Write-Step "VPS: $VpsProvider, domena: $VpsDomain, region: $VpsRegion" Cyan
    } else {
        Write-Step "Tryb lokalny (Ollama). Mozesz uruchomic provision-vps.ps1 pozniej z katalogu tools\." White
    }
    Write-Step "" White
}

if (-not (Test-Admin)) {
    if ($FromInstaller) {
        # Installer mode: file copy and SMB share are handled by admin [Run] entries in ISS
        # (install-share-admin.ps1 runs before this script). Just wait for share to appear.
        if (-not (Wait-AddinShare -Attempts 8 -DelayMilliseconds 500)) {
            $script:ShareReady = $false
        }
    } else {
        # Interactive mode: self-elevate to copy files and create the share
        Invoke-ElevatedPhase
        $SourceRoot = $InstallDir
        $ToolsDir = Join-Path $InstallDir "tools"
        if (-not (Wait-AddinShare -Attempts 4 -DelayMilliseconds 500)) {
            $script:ShareReady = $false
            Write-Step "OSTRZEZENIE: po etapie administratora biezacy profil nie widzi jeszcze \\localhost\$ShareName\manifest.xml." Yellow
        }
    }
} else {
    Copy-CSMFiles
    Grant-InstallAccess
    $shareOk = Ensure-Share
    if (-not $shareOk) { $script:ShareReady = $false }
}

# RC18: Desktop shortcut removed — the Word taskpane service panel (START/STOP/
# NAPRAW/CLEAN/DIAGNOZA) replaces the desktop launcher icon.  The script
# create-desktop-shortcut.ps1 is still shipped so advanced users can run it
# manually, but it is no longer called automatically during installation.
Run-SetupOnce
Assert-VenvReady
Clear-OfficeCache -LocalAppData $OriginalLocalAppData
Add-TrustedCatalogRegistry
Enable-Autostart
Start-CSM
# Provisioning VPS (opcjonalny — gdy wybrany podczas instalacji)
if ($VpsProvider -ne "") {
    Write-Step ""
    Write-Step "Rozpoczynanie provisioningu VPS ($VpsProvider)..." Cyan
    $provisionScript = Join-Path $ToolsDir "provision-vps.ps1"
    if (-not (Test-Path $provisionScript)) {
        Write-Step "BLAD: Nie znaleziono provision-vps.ps1 w $ToolsDir" Red
    } else {
        $provArgs = @(
            "-Provider", $VpsProvider,
            "-ApiKey",   $VpsApiKey,
            "-Domain",   $VpsDomain,
            "-InstallDir", $InstallDir
        )
        if ($VpsRegion -ne "") { $provArgs += @("-Region", $VpsRegion) }
        $provArgs += @(
            '-BielikModel', $BielikModel,
            '-EmbeddingProvider', $EmbeddingProvider,
            '-VoyageApiKey', $VoyageApiKey
        )
        try {
            & $script:psExe -NoProfile -ExecutionPolicy Bypass -File $provisionScript @provArgs
            Write-Step "Provisioning VPS zakonczony." Green
        } catch {
            Write-Step "BLAD provisioningu VPS: $_" Red
            Write-Step "Mozesz uruchomic provision-vps.ps1 recznie pozniej z katalogu tools\." Yellow
        }
    }
}

# Konfiguracja lokalnego modelu Bielik przez Ollama (tylko tryb lokalny)
if ($VpsProvider -eq "" -and $BielikModel -ne "") {
    Write-Step ""
    Write-Step "Konfiguracja lokalnego modelu Bielik ($BielikModel) przez Ollama..." Cyan
    $ollamaExe = "ollama"
    try {
        $ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
        $ollamaPath = if ($ollamaCmd) { $ollamaCmd.Source } else { $null }
        if (-not $ollamaPath) {
            Write-Step "OSTRZEZENIE: Nie znaleziono ollama w PATH. Model Bielik zostanie pobrany przy pierwszym uruchomieniu CSM." Yellow
        } else {
            # Sprawdz czy model juz istnieje — setup-once.ps1 mogl go juz pobrac
            $modelAlreadyPresent = $false
            try {
                $tagsResp = Invoke-WebRequest -Uri "http://127.0.0.1:11434/api/tags" -UseBasicParsing -TimeoutSec 4 -ErrorAction Stop
                $presentModels = ($tagsResp.Content | ConvertFrom-Json).models
                $modelAlreadyPresent = $null -ne ($presentModels | Where-Object { $_.name -match "(?i)bielik" })
            } catch {}

            if ($modelAlreadyPresent) {
                Write-Step "Model Bielik ($BielikModel) jest juz dostepny lokalnie." Green
            } else {
                Write-Step "Pobieranie modelu $BielikModel (moze zajac kilka minut przy pierwszym pobraniu)..." Yellow
                $stdoutFile2 = [System.IO.Path]::GetTempFileName()
                $stderrFile2 = [System.IO.Path]::GetTempFileName()
                try {
                    $pullProc = Start-Process -FilePath $ollamaExe -ArgumentList @("pull", $BielikModel) -NoNewWindow -PassThru -RedirectStandardOutput $stdoutFile2 -RedirectStandardError $stderrFile2
                    if (-not $pullProc.WaitForExit(600000)) {
                        try { $pullProc.Kill() } catch {}
                        Write-Step "OSTRZEZENIE: ollama pull przekroczyl limit czasu 10 minut. Model zostanie pobrany przy pierwszym uzyciu." Yellow
                    } elseif ($pullProc.ExitCode -eq 0) {
                        Write-Step "Model Bielik ($BielikModel) gotowy." Green
                    } else {
                        Write-Step "OSTRZEZENIE: ollama pull zakonczyl sie kodem $($pullProc.ExitCode). Model zostanie pobrany przy pierwszym uzyciu CSM." Yellow
                    }
                } finally {
                    Remove-Item -LiteralPath $stdoutFile2, $stderrFile2 -Force -ErrorAction SilentlyContinue
                }
            } # end else (model not yet present)
        }
    } catch {
        Write-Step "OSTRZEZENIE: nie udalo sie pobrac modelu Bielik przez Ollama: $($_.Exception.Message)" Yellow
        Write-Step "Model zostanie pobrany automatycznie przy pierwszym uzyciu CSM, jesli Ollama jest zainstalowane." Yellow
    }
}

Write-Step ""
if ($script:ShareReady) {
    Write-Step "Instalacja zakonczona." Green
    Write-Step "CSM zostal uruchomiony w tle i bedzie startowal automatycznie po zalogowaniu. Otworz Worda i wybierz dodatek CSM." Cyan
} else {
    Write-Step "Instalacja zakonczona z ostrzezeniem dotyczacym udzialu Worda." Yellow
    Write-Step "Skrot CSM i wpis Worda zostaly utworzone. Jesli Word nie widzi dodatku, uruchom CSM -> NAPRAW i przeslij log: $LogPath" Yellow
}
Write-Step "Na pulpicie uzytkownika pozostaje jedna ikona: CSM." Cyan
Write-Step "Jesli Word nie pokazuje dodatku: Wstawianie -> Moje dodatki -> Folder udostepniony -> Odswiez." Yellow
Write-SupportHint
