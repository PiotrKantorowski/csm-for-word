<#
Tworzy udzial SMB ClaudeSafeModeAddin -> {InstallDir}\addin.
Musi byc uruchomiony z uprawnieniami administratora.
Wywolywany przez instalator CSM-Setup.iss jako pierwszy krok admina (przed install-csm.ps1).
#>
param([string]$InstallDir = "C:\CSM")

$ErrorActionPreference = "SilentlyContinue"
$shareName = "ClaudeSafeModeAddin"
$addinDir  = Join-Path $InstallDir "addin"

# Upewnij sie ze katalog addin istnieje
if (-not (Test-Path $addinDir)) { exit 1 }

# Usun stary share jesli istnieje
$old = Get-SmbShare -Name $shareName -ErrorAction SilentlyContinue
if ($old) { Remove-SmbShare -Name $shareName -Force -ErrorAction SilentlyContinue }

# Probuj rozne nazwy konta (EN/PL Windows)
$candidates = @(
    @("Everyone"),
    @("Wszyscy"),
    @("BUILTIN\Users"),
    @("NT AUTHORITY\Authenticated Users")
)

$created = $false
if (Get-Command New-SmbShare -ErrorAction SilentlyContinue) {
    foreach ($accounts in $candidates) {
        try {
            New-SmbShare -Name $shareName -Path $addinDir -ReadAccess $accounts -ErrorAction Stop | Out-Null
            $created = $true
            break
        } catch {}
    }
}

if (-not $created) {
    foreach ($account in ($candidates | ForEach-Object { $_[0] })) {
        $r = cmd /c "net share $shareName=`"$addinDir`" /GRANT:`"$account`",READ" 2>&1
        if ($LASTEXITCODE -eq 0) { $created = $true; break }
    }
}

exit $(if ($created) { 0 } else { 1 })
