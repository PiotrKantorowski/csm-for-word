param(
    [switch]$NoOpenWord,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$StartScript = Join-Path $ScriptDir "start-claude-safe-mode.ps1"

$env:CSMW_ENABLE_BIELIK = "1"
if (-not $env:CSMW_BIELIK_PROVIDER) { $env:CSMW_BIELIK_PROVIDER = "ollama" }
if (-not $env:CSMW_BIELIK_MODEL) { $env:CSMW_BIELIK_MODEL = "hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M" }

& $StartScript @PSBoundParameters
