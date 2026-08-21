param(
    [string]$ModelName = "bielik",
    [string]$GgufPath = "",
    [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$RuntimeDir = Join-Path $Root "runtime"
$DefaultHfModel = "hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M"

Write-Host "CSM Bielik - konfiguracja opcjonalna" -ForegroundColor Cyan
Write-Host ""
Write-Host "CSM nie pakuje wag modelu do instalatora. Bielik dziala lokalnie przez Ollama albo serwer OpenAI-compatible." -ForegroundColor Yellow
Write-Host "Najprostszy wariant Ollama:" -ForegroundColor Yellow
Write-Host "  ollama run $DefaultHfModel" -ForegroundColor Gray
Write-Host "Potem uruchom: tools\start-claude-safe-mode-bielik.cmd" -ForegroundColor Gray
Write-Host ""

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    Write-Host "Nie znaleziono programu ollama w PATH. Zainstaluj Ollama albo uruchom Bielika w llama.cpp/LM Studio i ustaw CSMW_BIELIK_PROVIDER=openai." -ForegroundColor Yellow
    exit 0
}

if ($PrintOnly -or -not $GgufPath) {
    Write-Host "Ollama jest dostepna. Aby pobrac i uruchomic rekomendowany model, wykonaj:" -ForegroundColor Green
    Write-Host "  ollama run $DefaultHfModel" -ForegroundColor Gray
    Write-Host ""
    Write-Host "Jesli masz juz lokalny plik GGUF, uruchom:" -ForegroundColor Green
    Write-Host "  powershell -File tools\setup-bielik-optional.ps1 -GgufPath C:\sciezka\model.gguf -ModelName bielik" -ForegroundColor Gray
    exit 0
}

if (-not (Test-Path -LiteralPath $GgufPath)) {
    throw "Nie znaleziono pliku GGUF: $GgufPath"
}
if (-not (Test-Path -LiteralPath $RuntimeDir)) {
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
}

$modelfile = Join-Path $RuntimeDir "Bielik.Modelfile"
@"
FROM "$GgufPath"
PARAMETER temperature 0
PARAMETER num_ctx 8192
SYSTEM """Local PII detector for Polish legal documents. Return strict JSON only."""
"@ | Set-Content -Path $modelfile -Encoding UTF8

& ollama create $ModelName -f $modelfile
if ($LASTEXITCODE -ne 0) {
    throw "ollama create zakonczyl sie bledem."
}

Write-Host "Utworzono lokalny model Ollama: $ModelName" -ForegroundColor Green
Write-Host "Uruchamiaj CSM przez tools\start-claude-safe-mode-bielik.cmd albo ustaw CSMW_BIELIK_MODEL=$ModelName." -ForegroundColor Green
