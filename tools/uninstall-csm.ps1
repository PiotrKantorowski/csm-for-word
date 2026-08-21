param(
    [string]$InstallDir = "C:\CSM",
    [switch]$KeepData,
    [switch]$ElevatedPhase,
    [string]$OriginalDesktop = "",
    [string]$OriginalLocalAppData = ""
)

$ErrorActionPreference = "Continue"

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($id)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Remove-CsmGeneratedLocalhostCert {
    # Remove the localhost dev certificate that ensure-localhost-cert.ps1 added
    # to CurrentUser\Root and CurrentUser\TrustedPeople — but ONLY if CSM
    # generated it (verified by the marker file with the cert thumbprint).
    # Certificates created by other tools (e.g. office-addin-dev-certs npm
    # package) are left untouched so we never break unrelated Office add-ins.
    $certDir = Join-Path $env:USERPROFILE ".office-addin-dev-certs"
    $markerFile = Join-Path $certDir "csm-generated.txt"
    if (-not (Test-Path -LiteralPath $markerFile)) { return }

    $thumbprint = $null
    try {
        $line = (Get-Content -LiteralPath $markerFile -ErrorAction Stop |
                 Where-Object { $_ -match '^thumbprint=' } | Select-Object -First 1)
        if ($line) { $thumbprint = ($line -replace '^thumbprint=', '').Trim() }
    } catch {}
    if (-not $thumbprint) { return }

    foreach ($storeName in @("Root", "TrustedPeople")) {
        try {
            $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "CurrentUser")
            $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
            $found = @($store.Certificates | Where-Object { $_.Thumbprint -eq $thumbprint })
            foreach ($c in $found) { try { $store.Remove($c) } catch {} }
            $store.Close()
        } catch {}
    }

    # Remove the certificate files and marker on disk so a future reinstall
    # generates a fresh certificate (avoids stale-key issues).
    foreach ($f in @($markerFile,
                     (Join-Path $certDir "localhost.crt"),
                     (Join-Path $certDir "localhost.key"))) {
        if (Test-Path -LiteralPath $f) {
            try { Remove-Item -LiteralPath $f -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

function Remove-UserProfileArtifacts {
    param(
        [string]$DesktopPath = [Environment]::GetFolderPath("Desktop"),
        [string]$LocalAppDataPath = $env:LOCALAPPDATA
    )

    # This function intentionally runs in the original, non-elevated user context
    # whenever uninstall is launched from a standard session. TrustedCatalogs and
    # Desktop shortcuts are HKCU/user-profile artifacts; removing them only from
    # the elevated administrator profile would leave Word still pointing to CSM.
    # Autostart is a Task Scheduler artifact, not an HKCU artifact, so it is
    # removed only in Remove-MachineArtifacts to avoid a misleading duplicate
    # "not registered" message after it has already been removed.

    $base = "HKCU:\Software\Microsoft\Office\16.0\WEF\TrustedCatalogs"
    Get-ChildItem -Path $base -ErrorAction SilentlyContinue | ForEach-Object {
        try {
            $url = (Get-ItemProperty -Path $_.PSPath -ErrorAction SilentlyContinue).Url
            if ($url -like "*ClaudeSafeModeAddin*" -or $url -like "*CSMAddin*") {
                Remove-Item -Path $_.PSPath -Recurse -Force -ErrorAction SilentlyContinue
            }
        } catch {}
    }

    Remove-CsmGeneratedLocalhostCert

    if ($DesktopPath) {
        foreach ($name in @("CSM.lnk", "CSM - START.lnk", "CSM - STOP.lnk", "CSM-CLEAN.lnk", "CSM - CLEAN.lnk")) {
            $shortcut = Join-Path $DesktopPath $name
            if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force -ErrorAction SilentlyContinue }
        }
    }

    if ($LocalAppDataPath) {
        $officeBase = Join-Path $LocalAppDataPath "Microsoft\Office\16.0"
        foreach ($sub in @("Wef", "WebServiceCache", "OfficeFileCache")) {
            $path = Join-Path $officeBase $sub
            if (Test-Path -LiteralPath $path) {
                try { Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue } catch {}
            }
        }
    }
}

function Remove-MachineArtifacts {
    try { & (Join-Path $InstallDir "tools\stop-claude-safe-mode.ps1") } catch {}
    try { & (Join-Path $InstallDir "tools\unregister-autostart.ps1") -InstallDir $InstallDir -AllowMissing } catch {}

    try {
        $share = Get-SmbShare -Name "ClaudeSafeModeAddin" -ErrorAction SilentlyContinue
        if ($share) { Remove-SmbShare -Name "ClaudeSafeModeAddin" -Force }
    } catch {
        try { net.exe share ClaudeSafeModeAddin /delete /y | Out-Null } catch {}
    }

    if ((Test-Path -LiteralPath $InstallDir) -and -not $KeepData) {
        Remove-Item -LiteralPath $InstallDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

if (-not $OriginalDesktop) { $OriginalDesktop = [Environment]::GetFolderPath("Desktop") }
if (-not $OriginalLocalAppData) { $OriginalLocalAppData = $env:LOCALAPPDATA }

Get-Process -Name WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue

if ($ElevatedPhase) {
    if (-not (Test-Admin)) {
        Write-Host "BLAD: etap administratora uruchomiony bez uprawnien administratora." -ForegroundColor Red
        exit 1
    }
    Remove-MachineArtifacts
    Write-Host "Etap administratora zakonczony." -ForegroundColor Green
    exit 0
}

if (-not (Test-Admin)) {
    $args = @(
        "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`"",
        "-InstallDir", "`"$InstallDir`"",
        "-ElevatedPhase",
        "-OriginalDesktop", "`"$OriginalDesktop`"",
        "-OriginalLocalAppData", "`"$OriginalLocalAppData`""
    )
    if ($KeepData) { $args += "-KeepData" }
    $proc = Start-Process -FilePath "powershell.exe" -ArgumentList $args -Verb RunAs -Wait -PassThru
    if ($proc.ExitCode -ne 0) {
        Write-Host "BLAD: etap administratora odinstalowania zakonczyl sie kodem $($proc.ExitCode)." -ForegroundColor Red
        exit $proc.ExitCode
    }

    Remove-UserProfileArtifacts -DesktopPath $OriginalDesktop -LocalAppDataPath $OriginalLocalAppData
    Write-Host "CSM odinstalowany z profilu uzytkownika i usuniety z Worda." -ForegroundColor Green
    exit 0
}

# If the current user is already elevated, HKCU is also the profile being cleaned.
Remove-MachineArtifacts
Remove-UserProfileArtifacts -DesktopPath $OriginalDesktop -LocalAppDataPath $OriginalLocalAppData
Write-Host "CSM odinstalowany." -ForegroundColor Green
