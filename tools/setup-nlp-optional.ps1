$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$ServerDir = Join-Path $Root "server"
$VenvDir = Join-Path $ServerDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$NlpRequirements = Join-Path $ServerDir "requirements-nlp.txt"

if (!(Test-Path -LiteralPath $PythonExe)) {
  Write-Host "Nie znaleziono srodowiska Python. Uruchom najpierw setup-once.cmd" -ForegroundColor Red
  exit 1
}

if (Test-Path -LiteralPath $NlpRequirements) {
  & $PythonExe -m pip install -r $NlpRequirements
} else {
  & $PythonExe -m pip install spacy==3.7.6
}

# The model download uses spaCy's official package installer. It requires
# internet access and remains optional; core CSM works without this layer.
& $PythonExe -m spacy download pl_core_news_sm

Write-Host "Opcjonalna warstwa NLP zostala zainstalowana." -ForegroundColor Green
Write-Host "Aby wlaczyc spaCy przy starcie silnika, ustaw CSMW_ENABLE_SPACY=1 albo uzyj startu z NLP po pozniejszej konfiguracji." -ForegroundColor Yellow
Write-Host "Eksperymentalny skaner GLiNER jest opcjonalny: po recznej instalacji pakietu/modelu wlacz CSMW_ENABLE_GLINER=1." -ForegroundColor Yellow
