param(
    [string]$InnoSetupCompiler = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$Iss = Join-Path $ScriptDir "CSM-Setup.iss"

function Resolve-InnoSetupCompiler {
    param([string]$RequestedPath)

    if ($RequestedPath -and (Test-Path -LiteralPath $RequestedPath)) {
        return $RequestedPath
    }

    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path -LiteralPath $cmd.Source)) {
        return $cmd.Source
    }

    $candidates = @(
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Inno Setup 7\ISCC.exe"),
        (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe")
    )

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }

    throw "ISCC.exe not found. Install Inno Setup 6 or pass -InnoSetupCompiler."
}

if (-not (Test-Path -LiteralPath $Iss)) {
    throw "Installer script not found: $Iss"
}

$Compiler = Resolve-InnoSetupCompiler -RequestedPath $InnoSetupCompiler
Write-Host "Using Inno Setup Compiler: $Compiler" -ForegroundColor Cyan

& $Compiler $Iss
if ($LASTEXITCODE -ne 0) { throw "CSM installer build failed. Exit code: $LASTEXITCODE" }

$Expected = Join-Path $ScriptDir "output\CSM-Setup-v1.6.exe"
if (-not (Test-Path -LiteralPath $Expected)) {
    throw "Build completed but output file not found: $Expected"
}

# Inno Setup's CleanOutputDir=yes removes all files in output/ before building.
# Restore the sentinel README after each build so tests pass on the built tree.
$Readme = Join-Path $ScriptDir "output\README-SETUP-NOT-INCLUDED.txt"
Set-Content -Path $Readme -Encoding UTF8 -Value @"
Ten katalog zawiera pliki wyjsciowe instalatora CSM.

CSM-Setup-v1.6.exe - celowo nie ma go w repozytorium zrodlowym.
Plik instalatora jest generowany lokalnie przez skrypt build-csm-setup.ps1
i nie jest dolaczany do paczki zrodlowej.

Aby zbudowac instalator, uruchom:
  .\installer\build-csm-setup.ps1
"@

Write-Host "Done. Installer: $Expected" -ForegroundColor Green
