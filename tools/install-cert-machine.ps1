<#
Kopiuje certyfikat localhost z pliku CRT lub CurrentUser\Root do LocalMachine\Root.
Musi byc uruchomiony z uprawnieniami administratora.
Wywolywany przez instalator CSM-Setup.iss jako ostatni krok admina po instalacji.

Parametry:
  -CertDir    Katalog z plikiem localhost.crt (domyslnie: {localappdata}\.office-addin-dev-certs)
              Preferowane zrodlo — niezalezne od kontekstu uzytkownika.
  -Thumbprint Odcisk certyfikatu do wyszukania w Cert:\CurrentUser\Root (fallback).
#>
param(
    [string]$CertDir    = "",
    [string]$Thumbprint = ""
)

$ErrorActionPreference = "SilentlyContinue"

# --- Pobierz certyfikat ---
$cert = $null

# 1. Preferowane: zaladuj z pliku .crt (dziala niezaleznie od kontekstu admina vs uzytkownika)
if ($CertDir) {
    $crtPath = Join-Path $CertDir "localhost.crt"
    if (Test-Path $crtPath) {
        try {
            $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($crtPath)
        } catch { $cert = $null }
    }
}

# 2. Fallback: szukaj po thumbprincie lub nazwie w CurrentUser\Root
if (-not $cert) {
    if ($Thumbprint) {
        $cert = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $Thumbprint } | Select-Object -First 1
    } else {
        $cert = Get-ChildItem Cert:\CurrentUser\Root |
            Where-Object { $_.Subject -match "CN=localhost" } |
            Sort-Object NotAfter -Descending |
            Select-Object -First 1
    }
}

if (-not $cert) { exit 0 }  # Brak certyfikatu — nie blokuj instalacji

# --- Skopiuj do LocalMachine\Root i TrustedPeople ---
foreach ($storeName in @("Root", "TrustedPeople")) {
    try {
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "LocalMachine")
        $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
        $existing = @($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })
        if ($existing.Count -eq 0) { $store.Add($cert) }
        $store.Close()
    } catch { }
}

exit 0
