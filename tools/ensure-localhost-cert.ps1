param(
    [string]$CertDir = (Join-Path $env:USERPROFILE ".office-addin-dev-certs"),
    [int]$Days = 3650,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$CertFile = Join-Path $CertDir "localhost.crt"
$KeyFile = Join-Path $CertDir "localhost.key"
$MarkerFile = Join-Path $CertDir "csm-generated.txt"

function Write-Info([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::Cyan) {
    Write-Host $Message -ForegroundColor $Color
}

function ConvertTo-DerLength([int]$Length) {
    if ($Length -lt 128) { return [byte[]]@([byte]$Length) }
    $bytes = New-Object System.Collections.Generic.List[byte]
    $n = $Length
    while ($n -gt 0) {
        $bytes.Insert(0, [byte]($n -band 0xff))
        $n = $n -shr 8
    }
    return [byte[]](@([byte](0x80 -bor $bytes.Count)) + $bytes.ToArray())
}

function Join-Bytes([byte[][]]$Parts) {
    $list = New-Object System.Collections.Generic.List[byte]
    foreach ($part in $Parts) {
        if ($null -ne $part) { $list.AddRange([byte[]]$part) }
    }
    return [byte[]]$list.ToArray()
}

function New-DerElement([byte]$Tag, [byte[]]$Value) {
    return Join-Bytes @(([byte[]]@($Tag)), (ConvertTo-DerLength $Value.Length), $Value)
}

function New-DerInteger([byte[]]$Value) {
    if ($null -eq $Value -or $Value.Length -eq 0) { $Value = [byte[]]@(0) }
    $start = 0
    while (($start -lt ($Value.Length - 1)) -and ($Value[$start] -eq 0)) { $start++ }
    if ($start -gt 0) { $Value = [byte[]]$Value[$start..($Value.Length - 1)] }
    if (($Value[0] -band 0x80) -ne 0) { $Value = Join-Bytes @(([byte[]]@(0)), $Value) }
    return New-DerElement 0x02 $Value
}

function New-DerSequence([byte[]]$Value) {
    return New-DerElement 0x30 $Value
}

function New-DerGeneralNameDns([string]$Name) {
    $bytes = [System.Text.Encoding]::ASCII.GetBytes($Name)
    return New-DerElement 0x82 $bytes
}

function New-DerGeneralNameIp([string]$Address) {
    $ip = [System.Net.IPAddress]::Parse($Address)
    return New-DerElement 0x87 ([byte[]]$ip.GetAddressBytes())
}

function ConvertTo-Pem([string]$Label, [byte[]]$Der) {
    $b64 = [Convert]::ToBase64String($Der)
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("-----BEGIN $Label-----")
    for ($i = 0; $i -lt $b64.Length; $i += 64) {
        $len = [Math]::Min(64, $b64.Length - $i)
        $lines.Add($b64.Substring($i, $len))
    }
    $lines.Add("-----END $Label-----")
    return ($lines -join "`n") + "`n"
}

function Export-RsaPrivateKeyPkcs1([System.Security.Cryptography.RSA]$Rsa) {
    try {
        # PowerShell 7 / newer .NET
        return $Rsa.ExportRSAPrivateKey()
    } catch { }
    $p = $Rsa.ExportParameters($true)
    $body = Join-Bytes @(
        (New-DerInteger ([byte[]]@(0))),
        (New-DerInteger $p.Modulus),
        (New-DerInteger $p.Exponent),
        (New-DerInteger $p.D),
        (New-DerInteger $p.P),
        (New-DerInteger $p.Q),
        (New-DerInteger $p.DP),
        (New-DerInteger $p.DQ),
        (New-DerInteger $p.InverseQ)
    )
    return New-DerSequence $body
}

function Test-ExistingCertificateUsable {
    if ($Force) { return $false }
    if (-not (Test-Path -LiteralPath $CertFile) -or -not (Test-Path -LiteralPath $KeyFile)) { return $false }
    try {
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertFile)
        if ($cert.NotAfter -lt (Get-Date).AddDays(14)) { return $false }
        if ($cert.Subject -notmatch "CN=localhost") { return $false }
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
        try {
            $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
            $found = $store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint }
            return ($null -ne $found -and @($found).Count -gt 0)
        } finally {
            $store.Close()
        }
    } catch {
        return $false
    }
}

function Test-CertificateTrustedStrict {
    if (-not (Test-Path -LiteralPath $CertFile)) { return $false }
    try {
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertFile)
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
        try {
            $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadOnly)
            $found = @($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })
            return ($found.Count -gt 0)
        } finally { $store.Close() }
    } catch { return $false }
}

function Import-CertificateToUserStores {
    if (-not (Test-Path -LiteralPath $CertFile)) { return }
    $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertFile)
    foreach ($storeName in @("Root", "TrustedPeople")) {
        $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "CurrentUser")
        try {
            $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
            $existing = @($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })
            if ($existing.Count -eq 0) { $store.Add($cert) }
        } finally { $store.Close() }
    }
    # WebView2 (Word add-in host) requires LocalMachine\Root — try silently, needs admin
    foreach ($storeName in @("Root", "TrustedPeople")) {
        try {
            $lmStore = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "LocalMachine")
            $lmStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
            $lmExisting = @($lmStore.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })
            if ($lmExisting.Count -eq 0) { $lmStore.Add($cert) }
            $lmStore.Close()
        } catch { } # wymaga uprawnien admina — pomijamy jesli niedostepne
    }
}

function New-LocalhostCertificate {
    try {
        $null = [System.Security.Cryptography.X509Certificates.CertificateRequest]
    } catch {
        throw "Ten Windows/PowerShell nie udostepnia CertificateRequest. Zainstaluj aktualizacje .NET/Windows albo Node.js i uruchom NAPRAW."
    }

    New-Item -ItemType Directory -Force -Path $CertDir | Out-Null
    $rsa = [System.Security.Cryptography.RSA]::Create(2048)
    try {
        $dn = [System.Security.Cryptography.X509Certificates.X500DistinguishedName]::new("CN=localhost")
        $req = [System.Security.Cryptography.X509Certificates.CertificateRequest]::new(
            $dn,
            $rsa,
            [System.Security.Cryptography.HashAlgorithmName]::SHA256,
            [System.Security.Cryptography.RSASignaturePadding]::Pkcs1
        )
        $req.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509BasicConstraintsExtension]::new($false, $false, 0, $false))
        $req.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509KeyUsageExtension]::new(([System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::DigitalSignature -bor [System.Security.Cryptography.X509Certificates.X509KeyUsageFlags]::KeyEncipherment), $false))
        $oids = [System.Security.Cryptography.OidCollection]::new()
        $oids.Add([System.Security.Cryptography.Oid]::new("1.3.6.1.5.5.7.3.1", "Server Authentication")) | Out-Null
        $req.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509EnhancedKeyUsageExtension]::new($oids, $false))
        $san = New-DerSequence (Join-Bytes @(
            (New-DerGeneralNameDns "localhost"),
            (New-DerGeneralNameIp "127.0.0.1"),
            (New-DerGeneralNameIp "::1")
        ))
        $req.CertificateExtensions.Add([System.Security.Cryptography.X509Certificates.X509Extension]::new("2.5.29.17", $san, $false))
        $notBefore = (Get-Date).AddDays(-1)
        $notAfter = (Get-Date).AddDays($Days)
        $cert = $req.CreateSelfSigned($notBefore, $notAfter)
        $certDer = $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert)
        $keyDer = Export-RsaPrivateKeyPkcs1 -Rsa $rsa
        [System.IO.File]::WriteAllText($CertFile, (ConvertTo-Pem "CERTIFICATE" $certDer), (New-Object System.Text.UTF8Encoding($false)))
        [System.IO.File]::WriteAllText($KeyFile, (ConvertTo-Pem "RSA PRIVATE KEY" $keyDer), (New-Object System.Text.UTF8Encoding($false)))

        foreach ($storeName in @("Root", "TrustedPeople")) {
            $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "CurrentUser")
            try {
                $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
                $existing = @($store.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })
                if ($existing.Count -eq 0) { $store.Add($cert) }
            } finally {
                $store.Close()
            }
            # Try LocalMachine too (WebView2 requires it) — needs admin, skip if unavailable
            try {
                $lmStore = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, "LocalMachine")
                $lmStore.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
                $lmExisting = @($lmStore.Certificates | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })
                if ($lmExisting.Count -eq 0) { $lmStore.Add($cert) }
                $lmStore.Close()
            } catch { }
        }
        Set-Content -Path $MarkerFile -Value @(
            "generated_by=CSM",
            "created_at=$((Get-Date).ToString('s'))",
            "thumbprint=$($cert.Thumbprint)",
            "cert=$CertFile",
            "key=$KeyFile"
        ) -Encoding UTF8
        return $cert
    } finally {
        if ($null -ne $rsa) { $rsa.Dispose() }
    }
}

if (Test-ExistingCertificateUsable) {
    Write-Info "Certyfikat localhost dla CSM jest juz dostepny i zaufany: $CertFile" Green
    exit 0
}

Write-Info "Tworze lokalny certyfikat HTTPS dla https://localhost:3000 bez uzycia Node/npm..." Yellow
$created = New-LocalhostCertificate
Import-CertificateToUserStores
if (-not (Test-CertificateTrustedStrict)) {
    throw "Certyfikat localhost zostal utworzony, ale nie jest zaufany w magazynie CurrentUser\Root. Uruchom NAPRAW_CSM jako aktualny uzytkownik albo skontaktuj sie z administratorem."
}
Write-Info "Utworzono i zaufano certyfikat localhost w profilu uzytkownika. Thumbprint: $($created.Thumbprint)" Green
Write-Info "Certyfikat: $CertFile" Green
Write-Info "Klucz: $KeyFile" Green
exit 0
