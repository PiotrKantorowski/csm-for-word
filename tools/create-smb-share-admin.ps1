# Creates the local shared folder used by Word to discover the add-in.
# Run as Administrator.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$ToolsDir = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { $ScriptDir } else { Join-Path $Root "tools" }
$AddinDir = Join-Path $Root "addin"
$ShareName = "ClaudeSafeModeAddin"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$existing = Get-SmbShare -Name $ShareName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Udzial $ShareName juz istnieje. Usuwam i tworze ponownie..." -ForegroundColor Yellow
    Remove-SmbShare -Name $ShareName -Force
}

New-SmbShare -Name $ShareName -Path $AddinDir -ReadAccess $User
Write-Host "Utworzono udzial: \\localhost\$ShareName\" -ForegroundColor Green
Write-Host "Udzial wskazuje na: $AddinDir" -ForegroundColor Green
Write-Host "Uzytkownik z dostepem: $User"
Write-Host "Sprawdz w Eksploratorze: \\localhost\$ShareName\"
Write-Host "Pod tym adresem powinien byc widoczny bezposrednio plik manifest.xml" -ForegroundColor Yellow
