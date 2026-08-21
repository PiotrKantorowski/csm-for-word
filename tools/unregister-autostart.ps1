param(
    [string]$InstallDir = "C:\CSM",
    [switch]$Quiet,
    [switch]$AllowMissing
)

$ErrorActionPreference = "Continue"

$KnownTaskNames = @(
    "CSM AutoStart",
    "Claude Safe Mode AutoStart",
    "ClaudeSafeMode AutoStart",
    "Claude Safe Mode",
    "ClaudeSafeMode"
)

function Write-CsmAutostartMessage {
    param([string]$Message, [ConsoleColor]$Color = [ConsoleColor]::White)
    if (-not $Quiet) { Write-Host $Message -ForegroundColor $Color }
}

function Test-CsmScheduledTask {
    param($Task)
    if (-not $Task) { return $false }

    if ($KnownTaskNames -contains $Task.TaskName) { return $true }

    try {
        foreach ($action in @($Task.Actions)) {
            $text = (($action.Execute, $action.Arguments, $action.WorkingDirectory) -join " ")
            if ($text -match "(?i)start-claude-safe-mode\.ps1") { return $true }
            if ($text -match "(?i)ClaudeSafeModeAddin") { return $true }
            if ($InstallDir -and $text -like "*$InstallDir*") { return $true }
        }
    } catch {}

    return $false
}

$matches = @()

try {
    foreach ($name in $KnownTaskNames) {
        $matches += @(Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)
    }
} catch {}

try {
    $matches += @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { Test-CsmScheduledTask $_ })
} catch {}

$matches = @($matches | Where-Object { $_ } | Sort-Object TaskPath, TaskName -Unique)

if (-not $matches -or $matches.Count -eq 0) {
    Write-CsmAutostartMessage "Autostart CSM nie byl zarejestrowany - OK, nie ma czego usuwac." DarkGray
    if ($AllowMissing) { exit 0 }
    exit 0
}

$removed = 0
foreach ($task in $matches) {
    try {
        Unregister-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath -Confirm:$false -ErrorAction Stop
        $removed += 1
        Write-CsmAutostartMessage "Wylaczono autostart CSM: $($task.TaskPath)$($task.TaskName)" Green
    } catch {
        Write-CsmAutostartMessage "OSTRZEZENIE: nie udalo sie usunac autostartu CSM $($task.TaskPath)$($task.TaskName): $($_.Exception.Message)" Yellow
    }
}

if ($removed -eq 0) { exit 1 }
exit 0
