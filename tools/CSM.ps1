<#
CSM.ps1
Jedno okno serwisowe dla CSM po instalacji: START, STOP, CLEAN, NAPRAW, ODINSTALUJ.
CSM startuje automatycznie po zalogowaniu, a otwarcie panelu CSM samo uruchamia START,
jezeli uslugi nie sa jeszcze aktywne. Silnik CSM dziala w tle po START, nawet po zamknieciu tego okna.
#>

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { Split-Path -Parent $ScriptDir } else { $ScriptDir }
$ToolsDir = if ((Split-Path -Leaf $ScriptDir) -ieq "tools") { $ScriptDir } else { Join-Path $Root "tools" }
$SupportEmail = "csm@kancelariakantorowski.pl"
$SupportHint = "Jesli cos nie dziala, napisz na $SupportEmail - pomoze nam to rozwiazac Twoj problem."
$IconPath = Join-Path $Root "assets\csm.ico"
if (-not (Test-Path -LiteralPath $IconPath)) { $IconPath = Join-Path $Root "addin\assets\csm.ico" }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Start-CsmScript {
    param(
        [string]$ScriptName,
        [string]$Label,
        [string[]]$ExtraArgs = @(),
        [switch]$Hidden
    )
    $scriptPath = Join-Path $ToolsDir $ScriptName
    if (-not (Test-Path -LiteralPath $scriptPath)) {
        [System.Windows.Forms.MessageBox]::Show("Nie znaleziono pliku: $ScriptName`n`n$SupportHint", "CSM", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
        return
    }
    try {
        $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $scriptPath) + $ExtraArgs
        $startParams = @{
            FilePath = "powershell.exe"
            ArgumentList = $args
            WorkingDirectory = $Root
        }
        if ($Hidden) { $startParams.WindowStyle = "Hidden" }
        Start-Process @startParams
        $script:StatusLabel.Text = "Uruchomiono: $Label"
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show("Nie udalo sie uruchomic: $Label`n$($_.Exception.Message)`n`n$SupportHint", "CSM", [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Error) | Out-Null
    }
}

function Confirm-Action {
    param([string]$Message, [string]$Title = "CSM")
    $result = [System.Windows.Forms.MessageBox]::Show($Message, $Title, [System.Windows.Forms.MessageBoxButtons]::YesNo, [System.Windows.Forms.MessageBoxIcon]::Warning)
    return $result -eq [System.Windows.Forms.DialogResult]::Yes
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "CSM"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(460, 675)
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.BackColor = [System.Drawing.Color]::White
if (Test-Path -LiteralPath $IconPath) { try { $form.Icon = New-Object System.Drawing.Icon($IconPath) } catch {} }

$title = New-Object System.Windows.Forms.Label
$title.Text = "CSM for Word"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 18, [System.Drawing.FontStyle]::Bold)
$title.AutoSize = $true
$title.Location = New-Object System.Drawing.Point(30, 22)
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Po otwarciu tego panelu CSM sam uruchomi START, jesli uslugi nie dzialaja. STOP zatrzymuje uslugi."
$subtitle.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$subtitle.Size = New-Object System.Drawing.Size(390, 38)
$subtitle.Location = New-Object System.Drawing.Point(32, 62)
$form.Controls.Add($subtitle)

function New-CsmButton {
    param([string]$Text, [int]$Top, [System.Drawing.Color]$BackColor)
    $button = New-Object System.Windows.Forms.Button
    $button.Text = $Text
    $button.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
    $button.Size = New-Object System.Drawing.Size(380, 46)
    $button.Location = New-Object System.Drawing.Point(35, $Top)
    $button.BackColor = $BackColor
    $button.FlatStyle = "Flat"
    $button.FlatAppearance.BorderSize = 0
    $button.ForeColor = [System.Drawing.Color]::White
    return $button
}

$btnStart = New-CsmButton -Text "START - uruchom CSM w tle" -Top 110 -BackColor ([System.Drawing.Color]::FromArgb(4, 120, 87))
$btnStartBielik = New-CsmButton -Text "START + BIELIK - lokalny detektor" -Top 165 -BackColor ([System.Drawing.Color]::FromArgb(13, 148, 136))
$btnStop = New-CsmButton -Text "STOP - zatrzymaj CSM" -Top 220 -BackColor ([System.Drawing.Color]::FromArgb(30, 64, 175))
$btnClean = New-CsmButton -Text "CLEAN - wyczysc cache Worda" -Top 275 -BackColor ([System.Drawing.Color]::FromArgb(185, 28, 28))
$btnRepair = New-CsmButton -Text "NAPRAW - odswiez instalacje" -Top 330 -BackColor ([System.Drawing.Color]::FromArgb(99, 102, 241))
$btnDiag = New-CsmButton -Text "DIAGNOZA - sprawdz instalacje" -Top 385 -BackColor ([System.Drawing.Color]::FromArgb(217, 119, 6))
$btnUninstall = New-CsmButton -Text "ODINSTALUJ CSM" -Top 440 -BackColor ([System.Drawing.Color]::FromArgb(75, 85, 99))
$form.Controls.Add($btnStart)
$form.Controls.Add($btnStartBielik)
$form.Controls.Add($btnStop)
$form.Controls.Add($btnClean)
$form.Controls.Add($btnRepair)
$form.Controls.Add($btnDiag)
$form.Controls.Add($btnUninstall)

$script:StatusLabel = New-Object System.Windows.Forms.Label
$script:StatusLabel.Text = "Gotowe. Sprawdzam, czy CSM dziala; jesli nie, uruchomie START automatycznie."
$script:StatusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$script:StatusLabel.Size = New-Object System.Drawing.Size(390, 45)
$script:StatusLabel.Location = New-Object System.Drawing.Point(35, 505)
$form.Controls.Add($script:StatusLabel)

$supportLabel = New-Object System.Windows.Forms.Label
$supportLabel.Text = $SupportHint
$supportLabel.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$supportLabel.ForeColor = [System.Drawing.Color]::FromArgb(75, 85, 99)
$supportLabel.Size = New-Object System.Drawing.Size(390, 38)
$supportLabel.Location = New-Object System.Drawing.Point(35, 560)
$form.Controls.Add($supportLabel)

$support = New-Object System.Windows.Forms.Label
$support.Text = $SupportHint
$support.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Regular)
$support.ForeColor = [System.Drawing.Color]::FromArgb(153, 27, 27)
$support.Size = New-Object System.Drawing.Size(390, 42)
$support.Location = New-Object System.Drawing.Point(35, 560)
$form.Controls.Add($support)

$btnStart.Add_Click({ Start-CsmScript -ScriptName "start-claude-safe-mode.ps1" -Label "CSM - START" -ExtraArgs @("-NoOpenWord", "-NonInteractive") })
$btnStartBielik.Add_Click({ Start-CsmScript -ScriptName "start-claude-safe-mode-bielik.ps1" -Label "CSM - START + BIELIK" -ExtraArgs @("-NoOpenWord", "-NonInteractive") })
$btnStop.Add_Click({ Start-CsmScript -ScriptName "stop-claude-safe-mode.ps1" -Label "CSM - STOP" })
$btnClean.Add_Click({
    $message = "Czy na pewno chcesz wyczyscic cache dodatku CSM w Wordzie?`n`nWord zostanie zamkniety. Zapisz wczesniej otwarte dokumenty. CLEAN nie usuwa dokumentow ani plikow aplikacji CSM."
    if (Confirm-Action -Message $message -Title "Potwierdzenie CSM-CLEAN") {
        Start-CsmScript -ScriptName "CSM-CLEAN.ps1" -Label "CSM-CLEAN" -ExtraArgs @("-Force")
    } else { $script:StatusLabel.Text = "Anulowano CLEAN." }
})
$btnRepair.Add_Click({
    $message = "Czy uruchomic naprawe instalacji CSM?`n`nNaprawa odswiezy udzial Worda, wpis TrustedCatalogs, skrot CSM i cache dodatku."
    if (Confirm-Action -Message $message -Title "Napraw instalacje CSM") {
        Start-CsmScript -ScriptName "repair-csm.ps1" -Label "CSM - NAPRAW"
    } else { $script:StatusLabel.Text = "Anulowano naprawe." }
})
$btnDiag.Add_Click({ Start-CsmScript -ScriptName "diagnose-csm.ps1" -Label "CSM - DIAGNOZA" })

function Test-CsmHttpOk {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 300)
    } catch { return $false }
}

function Test-CsmTcpOpen {
    param([int]$Port)
    try {
        $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        return $null -ne $conn
    } catch { return $false }
}

function Test-CsmAlreadyRunning {
    return ((Test-CsmHttpOk -Url "http://127.0.0.1:8787/health") -and (Test-CsmTcpOpen -Port 3000))
}

$script:AutoStartAttempted = $false
function Start-CsmAutomaticallyOnOpen {
    if ($script:AutoStartAttempted) { return }
    $script:AutoStartAttempted = $true
    if (Test-CsmAlreadyRunning) {
        $script:StatusLabel.Text = "CSM juz dziala w tle. Mozesz przejsc do Worda."
        return
    }
    $script:StatusLabel.Text = "Uruchamiam START automatycznie w tle..."
    Start-CsmScript -ScriptName "start-claude-safe-mode.ps1" -Label "CSM - AUTO START" -ExtraArgs @("-NoOpenWord", "-NonInteractive") -Hidden
}

$btnUninstall.Add_Click({
    $message = "Czy na pewno odinstalowac CSM?`n`nZostanie usuniety udzial Worda, wpis TrustedCatalogs, skrot i katalog C:\CSM."
    if (Confirm-Action -Message $message -Title "Odinstaluj CSM") {
        Start-CsmScript -ScriptName "uninstall-csm.ps1" -Label "CSM - ODINSTALUJ"
        $form.Close()
    } else { $script:StatusLabel.Text = "Anulowano odinstalowanie." }
})

$form.Add_Shown({ Start-CsmAutomaticallyOnOpen })

[void]$form.ShowDialog()
