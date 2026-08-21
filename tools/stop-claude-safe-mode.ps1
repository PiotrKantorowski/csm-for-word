# Stops local services used by CSM for Word.

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$RuntimeDir = Join-Path $Root "runtime"

function Stop-PidFileProcess([string]$PidFile, [string]$Label) {
    if (-not (Test-Path -LiteralPath $PidFile)) { return }
    try {
        $pidText = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        $pidToStop = [int]$pidText
        if ($pidToStop -and $pidToStop -ne $PID) {
            try {
                Stop-Process -Id $pidToStop -Force -ErrorAction Stop
                Write-Host "Zatrzymano $Label (PID $pidToStop)." -ForegroundColor Green
            } catch {
                Write-Host "Nie udalo sie zatrzymac $Label (PID $pidToStop) albo proces juz nie dziala." -ForegroundColor Yellow
            }
        }
    } catch {}
    try { Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue } catch {}
}

Stop-PidFileProcess -PidFile (Join-Path $RuntimeDir "backend-wrapper.pid") -Label "proces startowy backendu CSM"
Stop-PidFileProcess -PidFile (Join-Path $RuntimeDir "addin-wrapper.pid") -Label "proces startowy serwera dodatku Word"

$ports = @(8787, 3000)
foreach ($port in $ports) {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($conn in $connections) {
        $pidToStop = $conn.OwningProcess
        if ($pidToStop) {
            try {
                Stop-Process -Id $pidToStop -Force
                Write-Host "Zatrzymano proces na porcie $port (PID $pidToStop)." -ForegroundColor Green
            } catch {
                Write-Host "Nie udalo sie zatrzymac procesu na porcie $port (PID $pidToStop)." -ForegroundColor Yellow
            }
        }
    }
}
Write-Host "Gotowe."
