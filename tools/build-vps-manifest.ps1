param(
    [Parameter(Mandatory=$true)]
    [string]$AddinBaseUrl,

    [Parameter(Mandatory=$true)]
    [string]$ApiBaseUrl,

    [string]$InstallDir = "",
    [string]$SourceManifest = "",
    [string]$OutputManifest = ""
)

$ErrorActionPreference = "Stop"

if (-not $InstallDir) {
    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $InstallDir = if ((Split-Path -Leaf $scriptDir) -ieq "tools") { Split-Path -Parent $scriptDir } else { $scriptDir }
}
if (-not $SourceManifest) { $SourceManifest = Join-Path $InstallDir "addin\manifest.xml" }
if (-not $OutputManifest) { $OutputManifest = Join-Path $InstallDir "addin\manifest-vps.xml" }

function Normalize-Origin([string]$Value) {
    $v = ($Value -as [string]).Trim().TrimEnd("/")
    if (-not $v) { throw "URL is required." }
    $uri = [Uri]$v
    return $uri.GetLeftPart([System.UriPartial]::Authority).TrimEnd("/")
}

$addinOrigin = Normalize-Origin $AddinBaseUrl
$apiOrigin = Normalize-Origin $ApiBaseUrl

[xml]$doc = Get-Content -LiteralPath $SourceManifest -Raw
$ns = New-Object System.Xml.XmlNamespaceManager($doc.NameTable)
$ns.AddNamespace("app", "http://schemas.microsoft.com/office/appforoffice/1.1")
$ns.AddNamespace("bt", "http://schemas.microsoft.com/office/officeappbasictypes/1.0")
$ns.AddNamespace("ov", "http://schemas.microsoft.com/office/taskpaneappversionoverrides")

foreach ($node in $doc.SelectNodes("//*[@DefaultValue]", $ns)) {
    $value = [string]$node.GetAttribute("DefaultValue")
    if ($value.StartsWith("https://localhost:3000")) {
        $updated = $value -replace "^https://localhost:3000", $addinOrigin
        $node.SetAttribute("DefaultValue", $updated)
    }
}

$appDomains = $doc.SelectSingleNode("/app:OfficeApp/app:AppDomains", $ns)
if ($null -eq $appDomains) {
    $officeApp = $doc.SelectSingleNode("/app:OfficeApp", $ns)
    $appDomains = $doc.CreateElement("AppDomains", "http://schemas.microsoft.com/office/appforoffice/1.1")
    [void]$officeApp.InsertBefore($appDomains, $officeApp.SelectSingleNode("app:Hosts", $ns))
}

foreach ($domain in @($appDomains.SelectNodes("app:AppDomain", $ns))) {
    $origin = $domain.InnerText.TrimEnd("/")
    if ($origin -in @("https://localhost:3000", "http://127.0.0.1:8787", "http://localhost:8787")) {
        [void]$appDomains.RemoveChild($domain)
    }
}

function Add-AppDomain([string]$Origin) {
    $exists = $false
    foreach ($domain in $appDomains.SelectNodes("app:AppDomain", $ns)) {
        if (($domain.InnerText.TrimEnd("/")) -ieq $Origin) { $exists = $true; break }
    }
    if (-not $exists) {
        $domain = $doc.CreateElement("AppDomain", "http://schemas.microsoft.com/office/appforoffice/1.1")
        $domain.InnerText = $Origin
        [void]$appDomains.AppendChild($domain)
    }
}

Add-AppDomain $addinOrigin
Add-AppDomain $apiOrigin

$dir = Split-Path -Parent $OutputManifest
if ($dir -and -not (Test-Path -LiteralPath $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

$settings = New-Object System.Xml.XmlWriterSettings
$settings.Encoding = New-Object System.Text.UTF8Encoding $false
$settings.Indent = $true
$writer = [System.Xml.XmlWriter]::Create($OutputManifest, $settings)
try {
    $doc.Save($writer)
} finally {
    $writer.Close()
}

Write-Host "CSM VPS manifest written: $OutputManifest"
