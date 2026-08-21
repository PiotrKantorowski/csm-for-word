<#
.SYNOPSIS
    Automatyczne tworzenie VPS dla CSM lub OLA na Hetzner Cloud albo IONOS Cloud.

.DESCRIPTION
    Tworzy VPS, instaluje zależności, konfiguruje Caddy (HTTPS) i uvicorn,
    następnie zwraca URL i token gotowy do podania w build-vps-manifest.ps1
    i write-vps-config.ps1.

.PARAMETER Provider
    'hetzner' lub 'ionos'.

.PARAMETER ApiKey
    Klucz API dostawcy. Dla Hetzner: wygeneruj w projekcie Cloud Console.
    Dla IONOS: wygeneruj w DCD > Profile > API Keys.

.PARAMETER Domain
    Pełna nazwa domeny (np. csm.kancelaria.pl). Musi wskazywać na nowy VPS
    przed uruchomieniem - skrypt poda wymagany adres IP do konfiguracji DNS.
    Caddy automatycznie pobierze certyfikat Let's Encrypt.

.PARAMETER Region
    Hetzner: fsn1 (Falkenstein, DE), nbg1 (Norymberga, DE), hel1 (Helsinki, FI).
    IONOS: de (Frankfurt), fr (Paryż). Domyślnie: fsn1 / de.

.PARAMETER Mode
    'csm' (domyślnie) lub 'ola'. Określa co zainstalować na serwerze.

.PARAMETER OutputFile
    Ścieżka do pliku JSON z wynikiem (URL, token, IP). Domyślnie: %TEMP%\csm-vps-result.json.

.PARAMETER InstallDir
    Katalog instalacji CSM (źródło plików do skopiowania na VPS).

.EXAMPLE
    .\provision-vps.ps1 -Provider hetzner -ApiKey "abc123" -Domain "csm.kancelaria.pl"
#>
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('hetzner', 'ionos')]
    [string]$Provider,

    [Parameter(Mandatory=$true)]
    [string]$ApiKey,

    [Parameter(Mandatory=$true)]
    [string]$Domain,

    [string]$Region = '',

    [ValidateSet('csm', 'ola')]
    [string]$Mode = 'csm',

    [string]$OutputFile = '',

    [string]$InstallDir = 'C:\CSM',

    # Model Bielik do zainstalowania na VPS przez Ollama
    [string]$BielikModel = 'hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M',

    # Silnik embeddingów: 'ollama' (nomic-embed-text-v2-moe, wielojezyczny, domyslny) lub 'voyage' (Voyage AI)
    [ValidateSet('ollama', 'voyage')]
    [string]$EmbeddingProvider = 'ollama',

    # Klucz API Voyage AI (wymagany gdy EmbeddingProvider = 'voyage')
    [string]$VoyageApiKey = ''
)

$ErrorActionPreference = 'Stop'

if (-not $OutputFile) {
    $OutputFile = Join-Path $env:TEMP 'csm-vps-result.json'
}

# --- helpers ----------------------------------------------------------------

function Write-VpsStep([string]$Msg, [string]$Color = 'White') {
    $ts = Get-Date -Format 'HH:mm:ss'
    Write-Host "[$ts] $Msg" -ForegroundColor $Color
}

function New-RandomToken([int]$Bytes = 32) {
    $arr = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($arr)
    return [Convert]::ToBase64String($arr) -replace '[+/=]', { @{'+' = '-'; '/' = '_'; '=' = ''}[$_.Value] }
}

function Wait-SshReady([string]$Ip, [int]$TimeoutSec = 300) {
    Write-VpsStep "Oczekiwanie na SSH na $Ip ..." Cyan
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $tcp = New-Object System.Net.Sockets.TcpClient
            $async = $tcp.BeginConnect($Ip, 22, $null, $null)
            $ok = $async.AsyncWaitHandle.WaitOne(3000, $false)
            $tcp.Close()
            if ($ok) { Write-VpsStep 'SSH dostepne.' Green; return $true }
        } catch {}
        Start-Sleep -Seconds 5
    }
    return $false
}

function Invoke-Ssh([string]$Ip, [string]$KeyFile, [string]$Command) {
    $result = & ssh -i $KeyFile -o StrictHostKeyChecking=no -o ConnectTimeout=15 `
        -o BatchMode=yes "root@$Ip" $Command 2>&1
    if ($LASTEXITCODE -ne 0) { throw "SSH command failed (code $LASTEXITCODE): $result" }
    return $result
}

function Copy-DirToVps([string]$LocalDir, [string]$Ip, [string]$KeyFile, [string]$RemotePath) {
    & scp -i $KeyFile -o StrictHostKeyChecking=no -r "$LocalDir" "root@${Ip}:${RemotePath}" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "SCP failed for $LocalDir -> $RemotePath" }
}

function ConvertTo-ShellSingleQuoted([string]$Value) {
    $escaped = ($Value -as [string]).Replace("'", "'`"`"`'`"`"`'")
    return "'" + $escaped + "'"
}

# --- SSH key generation ------------------------------------------------------

function New-TempSshKey {
    $keyDir = Join-Path $env:TEMP 'csm-vps-key'
    New-Item -ItemType Directory -Path $keyDir -Force | Out-Null
    $keyFile = Join-Path $keyDir 'id_ed25519'
    if (Test-Path $keyFile) { Remove-Item $keyFile, "$keyFile.pub" -Force }
    & ssh-keygen -t ed25519 -N '' -f $keyFile -C 'csm-vps-provisioner' 2>&1 | Out-Null
    if (-not (Test-Path $keyFile)) { throw 'ssh-keygen nie powiodlo sie. Upewnij sie ze OpenSSH jest zainstalowany (Windows 10+).' }
    $pub = Get-Content "$keyFile.pub"
    return @{ Private = $keyFile; Public = $pub }
}

# --- cloud-init template -----------------------------------------------------

function Build-CloudInit([string]$ApiToken, [string]$EncKey, [string]$Domain,
                          [string]$EmbeddingProv = 'ollama', [string]$VoyageKey = '',
                          [string]$Model = '') {
    return @"
#cloud-config
locale: pl_PL.UTF-8
timezone: Europe/Warsaw

packages:
  - python3
  - python3-pip
  - python3-venv
  - debian-keyring
  - debian-archive-keyring
  - apt-transport-https
  - curl
  - ufw

runcmd:
  # Caddy
  - curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  - curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
  - apt-get update -qq && apt-get install -y caddy
  # Ollama
  - curl -fsSL https://ollama.com/install.sh | sh
  - systemctl enable ollama --now
  # CSM user
  - useradd -m -s /bin/bash csm
  - mkdir -p /opt/csm /opt/ola /srv/csm/data /srv/ola/rag/data /srv/ola/knowledge/rag
  - chown -R csm:csm /opt/csm /opt/ola /srv/csm /srv/ola
  # Python venv (packages installed later after SCP)
  - python3 -m venv /opt/csm/venv
  # Firewall
  - ufw allow 22/tcp
  - ufw allow 80/tcp
  - ufw allow 443/tcp
  - ufw --force enable
  # Enable services (start after SCP)
  - systemctl daemon-reload

write_files:
  - path: /opt/csm/.env
    permissions: '0600'
    owner: csm:csm
    content: |
      CSM_REMOTE_MODE=1
      CSM_API_TOKEN=${ApiToken}
      CSM_MAP_ENCRYPTION_KEY=${EncKey}
      CSM_ALLOWED_ORIGINS=https://${Domain}
      CSM_PUBLIC_API_URL=https://${Domain}
      CSM_BASE_DIR=/srv/csm/data
      EMBEDDING_PROVIDER=${EmbeddingProv}
      VOYAGE_API_KEY=${VoyageKey}
      OLLAMA_HOST=http://127.0.0.1:11434
      BIELIK_MODEL=${Model}
      CSMW_ENABLE_BIELIK=1
      CSMW_BIELIK_PROVIDER=ollama
      CSMW_BIELIK_MODEL=${Model}
      CSMW_BIELIK_URL=http://127.0.0.1:11434/api/chat

  - path: /etc/systemd/system/csm-api.service
    content: |
      [Unit]
      Description=CSM API Server
      After=network.target
      [Service]
      Type=simple
      User=csm
      WorkingDirectory=/opt/csm/server
      EnvironmentFile=/opt/csm/.env
      ExecStart=/opt/csm/venv/bin/python -m uvicorn api:app --host 127.0.0.1 --port 8787
      Restart=always
      RestartSec=5
      [Install]
      WantedBy=multi-user.target

  - path: /etc/caddy/Caddyfile
    content: |
      ${Domain} {
          # CSM: sciezki API (handle = idiomatic Caddy v2, mutually exclusive blocks)
          handle /health* { reverse_proxy 127.0.0.1:8787 }
          handle /auth* { reverse_proxy 127.0.0.1:8787 }
          handle /mask* { reverse_proxy 127.0.0.1:8787 }
          handle /restore* { reverse_proxy 127.0.0.1:8787 }
          handle /scan* { reverse_proxy 127.0.0.1:8787 }
          handle /v2/* { reverse_proxy 127.0.0.1:8787 }
          handle /v4/* { reverse_proxy 127.0.0.1:8787 }
          handle /placeholder* { reverse_proxy 127.0.0.1:8787 }
          handle /original* { reverse_proxy 127.0.0.1:8787 }
          handle /backup* { reverse_proxy 127.0.0.1:8787 }
          handle /audit* { reverse_proxy 127.0.0.1:8787 }
          handle /docx* { reverse_proxy 127.0.0.1:8787 }
          # OLA: MCP gateway
          handle /mcp* {
              @missingAuth not header Authorization "Bearer ${ApiToken}"
              respond @missingAuth "Unauthorized" 401
              reverse_proxy 127.0.0.1:9090
          }
          # Pliki statyczne (CSM addin lub strona info)
          handle {
              root * /srv/csm/addin
              file_server
          }
      }
"@
}

# --- Hetzner provisioning ---------------------------------------------------

function New-HetznerVps([string]$ApiKey, [string]$Region, [string]$PublicKey, [string]$CloudInit, [string]$ServerType = 'cx23') {
    if (-not $Region) { $Region = 'fsn1' }  # Falkenstein, Niemcy (domyslny)

    $headers = @{ Authorization = "Bearer $ApiKey"; 'Content-Type' = 'application/json' }

    # Walidacja klucza
    try {
        Invoke-RestMethod 'https://api.hetzner.cloud/v1/servers?page=1&per_page=1' -Headers $headers -TimeoutSec 15 | Out-Null
    } catch {
        throw "Nieprawidlowy klucz API Hetzner lub brak polaczenia: $_"
    }

    # Upload klucza SSH
    $keyName = "csm-provision-$(Get-Date -Format 'yyyyMMddHHmmss')"
    $sshKeyBody = @{ name = $keyName; public_key = $PublicKey } | ConvertTo-Json
    $sshKeyResp = Invoke-RestMethod 'https://api.hetzner.cloud/v1/ssh_keys' -Method POST -Headers $headers -Body $sshKeyBody -TimeoutSec 15
    $sshKeyId = $sshKeyResp.ssh_key.id

    # Tworzenie serwera
    $serverName = "csm-$(Get-Random -Maximum 9999)"
    $body = @{
        name        = $serverName
        server_type = $ServerType
        location    = $Region
        image       = 'ubuntu-24.04'
        user_data   = $CloudInit
        ssh_keys    = @($sshKeyId)
        start_after_create = $true
    } | ConvertTo-Json -Depth 5
    $resp = Invoke-RestMethod 'https://api.hetzner.cloud/v1/servers' -Method POST -Headers $headers -Body $body -TimeoutSec 30
    $serverId = $resp.server.id
    $serverIp = $resp.server.public_net.ipv4.ip
    Write-VpsStep "Serwer Hetzner utworzony: ID=$serverId, IP=$serverIp, region=$Region" Green

    # Czekaj az serwer bedzie running
    Write-VpsStep 'Oczekiwanie na uruchomienie serwera (max 3 min)...' Cyan
    $deadline = (Get-Date).AddMinutes(3)
    while ((Get-Date) -lt $deadline) {
        Start-Sleep -Seconds 8
        $s = Invoke-RestMethod "https://api.hetzner.cloud/v1/servers/$serverId" -Headers $headers -TimeoutSec 15
        if ($s.server.status -eq 'running') { break }
        Write-VpsStep "  status: $($s.server.status)..." Gray
    }

    # Usun klucz SSH z projektu (uzywany tylko jednorazowo)
    try { Invoke-RestMethod "https://api.hetzner.cloud/v1/ssh_keys/$sshKeyId" -Method DELETE -Headers $headers | Out-Null } catch {}

    return $serverIp
}

# --- IONOS provisioning -----------------------------------------------------

function New-IonOsVps([string]$ApiKey, [string]$Region, [string]$PublicKey, [string]$CloudInit,
                       [int]$IonosRam = 4096, [int]$IonosCores = 2) {
    if (-not $Region) { $Region = 'de' }  # Frankfurt, Niemcy

    $regionMap = @{ de = '15f67991-0f51-4910-a201-f013c6a36b49'; fr = 'f10a2b87-ac8d-4f50-ad4e-97eb68fe4d6e' }
    if (-not $regionMap.ContainsKey($Region)) { throw "Nieznany region IONOS: $Region. Uzyj: de, fr" }

    # IONOS API v6 — Basic Auth: username:password lub token jako username z pustym password
    $cred = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("$($ApiKey):"))
    $headers = @{ Authorization = "Basic $cred"; 'Content-Type' = 'application/json' }

    # Tworzenie data center
    $dcBody = @{ properties = @{ name = 'CSM-DC'; location = $Region } } | ConvertTo-Json
    $dc = Invoke-RestMethod 'https://api.ionos.com/cloudapi/v6/datacenters' -Method POST -Headers $headers -Body $dcBody -TimeoutSec 30
    $dcId = $dc.id

    # Tworzenie serwera (IONOS wymaga osobnych krolow: server + NIC + volume)
    $srvBody = @{ properties = @{
        name = 'csm-server'; cores = $IonosCores; ram = $IonosRam
        bootVolume = $null; availabilityZone = 'AUTO'
    }} | ConvertTo-Json -Depth 5
    $srv = Invoke-RestMethod "https://api.ionos.com/cloudapi/v6/datacenters/$dcId/servers" -Method POST -Headers $headers -Body $srvBody -TimeoutSec 30
    $srvId = $srv.id

    # Volume z Ubuntu 24.04
    $volBody = @{ properties = @{
        name = 'csm-boot'; type = 'SSD Standard'; size = 50
        image = '9c5b1b10-c61f-11e9-b3a0-52540005ab80'  # Ubuntu 24.04 DE
        imagePassword = (New-RandomToken 12)
        sshKeys = @($PublicKey)
        userData = $CloudInit
    }} | ConvertTo-Json -Depth 5
    $vol = Invoke-RestMethod "https://api.ionos.com/cloudapi/v6/datacenters/$dcId/volumes" -Method POST -Headers $headers -Body $volBody -TimeoutSec 30
    $volId = $vol.id

    # Attach volume + boot
    $attachBody = @{ id = $volId } | ConvertTo-Json
    Invoke-RestMethod "https://api.ionos.com/cloudapi/v6/datacenters/$dcId/servers/$srvId/volumes" -Method POST -Headers $headers -Body $attachBody -TimeoutSec 30 | Out-Null

    # NIC (publiczny IP)
    $nicBody = @{ properties = @{ name = 'nic0'; lan = 1 } } | ConvertTo-Json
    Invoke-RestMethod "https://api.ionos.com/cloudapi/v6/datacenters/$dcId/servers/$srvId/nics" -Method POST -Headers $headers -Body $nicBody -TimeoutSec 30 | Out-Null

    # Czekaj na IP (max 5 min)
    Write-VpsStep 'Oczekiwanie na IP serwera IONOS...' Cyan
    $ip = $null
    $deadline = (Get-Date).AddMinutes(5)
    while ((Get-Date) -lt $deadline -and -not $ip) {
        Start-Sleep -Seconds 12
        $info = Invoke-RestMethod "https://api.ionos.com/cloudapi/v6/datacenters/$dcId/servers/$srvId/nics" -Headers $headers -TimeoutSec 15
        $ip = $info.items | ForEach-Object { $_.properties.ips } | Where-Object { $_ } | Select-Object -First 1
    }
    if (-not $ip) { throw 'Nie udalo sie uzyskac IP serwera IONOS w limicie czasu.' }

    Write-VpsStep "Serwer IONOS utworzony: IP=$ip, region=$Region" Green
    return $ip
}

# --- remote setup after SSH --------------------------------------------------

function Install-CsmOnVps([string]$Ip, [string]$KeyFile, [string]$InstallDir) {
    Write-VpsStep 'Kopiowanie plikow serwera na VPS...' Cyan

    # Kopiuj katalog server/
    $serverDir = Join-Path $InstallDir 'server'
    if (-not (Test-Path $serverDir)) { throw "Nie znaleziono katalogu serwera: $serverDir" }
    Copy-DirToVps $serverDir $Ip $KeyFile '/opt/csm/'

    # Kopiuj katalog addin/ (pliki statyczne dla Worda)
    $addinDir = Join-Path $InstallDir 'addin'
    if (Test-Path $addinDir) {
        Invoke-Ssh $Ip $KeyFile 'mkdir -p /srv/csm/addin'
        Copy-DirToVps $addinDir $Ip $KeyFile '/srv/csm/'
        Invoke-Ssh $Ip $KeyFile 'chown -R csm:csm /srv/csm/addin'
    }

    Write-VpsStep 'Instalowanie pakietow Python (pip)...' Cyan
    Invoke-Ssh $Ip $KeyFile '/opt/csm/venv/bin/pip install --quiet -r /opt/csm/server/requirements-runtime.txt 2>&1'

    Write-VpsStep 'Ustawianie uprawnien...' Cyan
    Invoke-Ssh $Ip $KeyFile @'
chown -R csm:csm /opt/csm
chmod 600 /opt/csm/.env
systemctl daemon-reload
systemctl enable csm-api
systemctl start csm-api
systemctl reload caddy || systemctl restart caddy
'@
    Write-VpsStep 'Uslugi uruchomione.' Green
}

# --- OLA remote setup -------------------------------------------------------

function Install-OlaOnVps([string]$Ip, [string]$KeyFile, [string]$InstallDir, [string]$ApiToken,
                         [string]$BielikModelTag = 'hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M',
                         [string]$EmbeddingProv = 'ollama',
                         [string]$VoyageKey = '') {
    Write-VpsStep 'Kopiowanie plikow OLA na VPS...' Cyan

    # Zainstaluj Node.js LTS
    Invoke-Ssh $Ip $KeyFile @'
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
node --version
'@

    # Kopiuj katalogi OLA
    foreach ($dir in @('modules', 'src', 'scripts')) {
        $localDir = Join-Path $InstallDir $dir
        if (Test-Path $localDir) {
            Invoke-Ssh $Ip $KeyFile "mkdir -p /opt/ola/$dir"
            Copy-DirToVps $localDir $Ip $KeyFile "/opt/ola/"
        }
    }

    # package.json i node_modules
    $pkgJson = Join-Path $InstallDir 'package.json'
    if (Test-Path $pkgJson) {
        & scp -i $KeyFile -o StrictHostKeyChecking=no $pkgJson "root@${Ip}:/opt/ola/" 2>&1 | Out-Null
    }
    $pkgLock = Join-Path $InstallDir 'package-lock.json'
    if (Test-Path $pkgLock) {
        & scp -i $KeyFile -o StrictHostKeyChecking=no $pkgLock "root@${Ip}:/opt/ola/" 2>&1 | Out-Null
    }
    $modulesEnv = Join-Path $InstallDir 'modules.env'
    if (Test-Path $modulesEnv) {
        & scp -i $KeyFile -o StrictHostKeyChecking=no $modulesEnv "root@${Ip}:/opt/ola/modules.env.import" 2>&1 | Out-Null
    }

    Invoke-Ssh $Ip $KeyFile @'
cd /opt/ola && npm install --omit=dev 2>&1 | tail -5
# Build modules
for d in modules/mcp-*/; do
    [ -f "$d/package.json" ] && (cd "$d" && npm install --omit=dev && npx tsc 2>/dev/null || true)
done
chown -R csm:csm /opt/ola
'@

    $modelQ = ConvertTo-ShellSingleQuoted $BielikModelTag
    $embedQ = ConvertTo-ShellSingleQuoted $EmbeddingProv
    $voyageQ = ConvertTo-ShellSingleQuoted $VoyageKey
    Invoke-Ssh $Ip $KeyFile @"
cd /opt/ola
if [ -f /opt/ola/scripts/build-remote-mcp-config.mjs ]; then
  REMOTE_VOYAGE_API_KEY=$voyageQ /usr/bin/node /opt/ola/scripts/build-remote-mcp-config.mjs --root /opt/ola --rag-home /srv/ola/rag --modules-env /opt/ola/modules.env --import-env /opt/ola/modules.env.import --bielik-model $modelQ --embedding-provider $embedQ
fi
chown -R csm:csm /opt/ola /srv/ola
[ -f /opt/ola/modules.env ] && chmod 600 /opt/ola/modules.env
"@

    Write-VpsStep 'Konfigurowanie OLA Gateway (HTTP MCP)...' Cyan

    # Serwis OLA MCP gateway: native HTTP mode from mcp-all-in-one.
    Invoke-Ssh $Ip $KeyFile @"
cat > /etc/systemd/system/ola-gateway.service << 'EOF'
[Unit]
Description=OLA MCP Gateway
After=network.target ollama.service
[Service]
Type=simple
User=csm
WorkingDirectory=/opt/ola
Environment=OLA_GATEWAY_TOKEN=$ApiToken
Environment=OLA_GATEWAY_PORT=9090
Environment=OLA_MODULES_ENV=/opt/ola/modules.env
Environment=OLA_RAG_HOME=/srv/ola/rag
Environment=CHROMA_PERSIST_DIR=/srv/ola/rag/chroma_db
Environment=COLLECTION_NAME=ola_rag
ExecStart=/usr/bin/node /opt/ola/node_modules/mcp-all-in-one/dist/index.js http --host 127.0.0.1 --port 9090 --silent --log-level error --mcp-config /opt/ola/mcp-all-in-one.json
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable ola-gateway
systemctl start ola-gateway
"@

    # Caddy dla OLA (MCP endpoint pod /mcp) — domena przekazana przez parametr zewnetrzny
    # Zapisana przez Build-CloudInit juz w Caddyfile; tylko przeladuj
    Invoke-Ssh $Ip $KeyFile 'systemctl reload caddy || systemctl restart caddy'

    Write-VpsStep 'OLA Gateway uruchomiony.' Green
}

# --- DNS instruction ---------------------------------------------------------

function Show-DnsInstruction([string]$Ip, [string]$Domain) {
    Write-Host ''
    Write-Host '=========================================================' -ForegroundColor Yellow
    Write-Host " WYMAGANA AKCJA: skonfiguruj DNS przed kontynuacja" -ForegroundColor Yellow
    Write-Host '=========================================================' -ForegroundColor Yellow
    Write-Host " Dodaj rekord A w panelu DNS swojej domeny:" -ForegroundColor Cyan
    Write-Host "   $Domain  ->  $Ip  (TTL: 300)" -ForegroundColor White
    Write-Host ''
    Write-Host " Sprawdz propagacje DNS: nslookup $Domain" -ForegroundColor Gray
    Write-Host '=========================================================`n' -ForegroundColor Yellow
    Read-Host 'Nacisnij ENTER gdy rekord A jest juz aktywny (ping $Domain zwraca $Ip)...'
}

# --- server sizing based on model -----------------------------------------------

function Get-VpsSpecs([string]$Model) {
    if ($Model -match '11[Bb]') {
        return @{ HetznerType = 'cx33'; IonosRam = 8192; IonosCores = 4;
                  Note = '11B: cx33 / 8 GB RAM (~6,49 EUR/mies.)' }
    }
    if ($Model -match '4\.5[Bb]') {
        return @{ HetznerType = 'cx33'; IonosRam = 8192; IonosCores = 4;
                  Note = '4.5B: cx33 / 8 GB RAM (~6,49 EUR/mies.)' }
    }
    if ($Model -match '7[Bb]') {
        return @{ HetznerType = 'cx33'; IonosRam = 8192; IonosCores = 4;
                  Note = '7B: cx33 / 8 GB RAM (~6,49 EUR/mies.)' }
    }
    return @{ HetznerType = 'cx23'; IonosRam = 4096; IonosCores = 2;
              Note = '1.5B: cx23 / 4 GB RAM (~3,99 EUR/mies.)' }
}

function Install-BielikModel([string]$Ip, [string]$KeyFile, [string]$Model) {
    if ([string]::IsNullOrEmpty($Model)) { return }
    Write-VpsStep "Pobieranie modelu Bielik: $Model" Cyan
    Write-VpsStep "(Moze trwac 10-20 min dla 11B — plik ~7 GB)" Yellow
    Invoke-Ssh $Ip $KeyFile "ollama pull '$Model' 2>&1 | tail -5"
    Write-VpsStep "Model Bielik zainstalowany." Green
}

# --- main -------------------------------------------------------------------

Write-VpsStep "Provisioning VPS: provider=$Provider, region=$Region, domain=$Domain, mode=$Mode" Cyan

# 1. Generuj sekrety
$apiToken  = New-RandomToken 32
$encKey    = New-RandomToken 32
Write-VpsStep 'Sekrety wygenerowane.' Green

# 2. Klucz SSH (tymczasowy)
Write-VpsStep 'Generowanie tymczasowego klucza SSH...' Cyan
$sshKey = New-TempSshKey

# 3. Cloud-init + dobor rozmiaru serwera
$specs     = Get-VpsSpecs -Model $BielikModel
Write-VpsStep "Typ serwera: Hetzner=$($specs.HetznerType) / IONOS RAM=$($specs.IonosRam)MB ($($specs.Note))" Cyan
$cloudInit = Build-CloudInit -ApiToken $apiToken -EncKey $encKey -Domain $Domain `
             -EmbeddingProv $EmbeddingProvider -VoyageKey $VoyageApiKey -Model $BielikModel

# 4. Tworzenie VPS
$serverIp = switch ($Provider) {
    'hetzner' { New-HetznerVps -ApiKey $ApiKey -Region $Region -PublicKey $sshKey.Public -CloudInit $cloudInit -ServerType $specs.HetznerType }
    'ionos'   { New-IonOsVps  -ApiKey $ApiKey -Region $Region -PublicKey $sshKey.Public -CloudInit $cloudInit -IonosRam $specs.IonosRam -IonosCores $specs.IonosCores }
}

# 5. DNS instruction
Show-DnsInstruction -Ip $serverIp -Domain $Domain

# 6. Czekaj na SSH
if (-not (Wait-SshReady -Ip $serverIp -TimeoutSec 300)) {
    throw "Timeout oczekiwania na SSH ($serverIp). Sprawdz czy VPS uruchomil sie poprawnie."
}

# 7. Czekaj az cloud-init sie zakonczy (usuwa /run/cloud-init/result.json gdy ready)
Write-VpsStep 'Czekanie na zakonczenie cloud-init (max 5 min)...' Cyan
$deadline = (Get-Date).AddMinutes(5)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 10
    try {
        $status = Invoke-Ssh $serverIp $sshKey.Private 'cloud-init status 2>/dev/null || echo done'
        if ($status -match 'done|error') { break }
    } catch {}
}

# 8. Upload i konfiguracja
if ($Mode -eq 'csm') {
    Install-CsmOnVps -Ip $serverIp -KeyFile $sshKey.Private -InstallDir $InstallDir
} else {
    Install-OlaOnVps -Ip $serverIp -KeyFile $sshKey.Private -InstallDir $InstallDir -ApiToken $apiToken `
                     -BielikModelTag $BielikModel -EmbeddingProv $EmbeddingProvider -VoyageKey $VoyageApiKey
}

# 8b. Pull modelu Bielik (po zakonczeniu glownej konfiguracji)
Install-BielikModel -Ip $serverIp -KeyFile $sshKey.Private -Model $BielikModel

# 8c. Pull modelu embeddingów (Ollama; nomic-embed-text-v2-moe = wielojezyczny, lepszy dla polskiego)
if ($EmbeddingProvider -eq 'ollama') {
    Write-VpsStep 'Pobieranie modelu embeddingów: nomic-embed-text-v2-moe (wielojezyczny)...' Cyan
    Invoke-Ssh $serverIp $sshKey.Private "ollama pull 'nomic-embed-text-v2-moe' 2>&1 | tail -3"
    Write-VpsStep 'Model embeddingów zainstalowany.' Green
}

# 9. Konfiguruj addin / manifest lokalnie
$addinBaseUrl = "https://$Domain"
$apiBaseUrl   = "https://$Domain"

if ($Mode -eq 'csm') {
    Write-VpsStep 'Generowanie konfiguracji CSM dla addinu Worda...' Cyan
    $writeVpsConfig = Join-Path $InstallDir 'tools\write-vps-config.ps1'
    if (Test-Path $writeVpsConfig) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $writeVpsConfig `
            -ApiBaseUrl $apiBaseUrl -ApiToken $apiToken | Out-Null
    }
    $buildManifest = Join-Path $InstallDir 'tools\build-vps-manifest.ps1'
    if (Test-Path $buildManifest) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $buildManifest `
            -AddinBaseUrl $addinBaseUrl -ApiBaseUrl $apiBaseUrl | Out-Null
    }
}

# 10. Usun tymczasowy klucz SSH
Remove-Item (Split-Path $sshKey.Private -Parent) -Recurse -Force -ErrorAction SilentlyContinue
Write-VpsStep 'Tymczasowy klucz SSH usuniety.' Gray

# 11. Zapisz wynik
$result = @{
    provider          = $Provider
    serverIp          = $serverIp
    domain            = $Domain
    addinUrl          = $addinBaseUrl
    apiUrl            = $apiBaseUrl
    apiToken          = $apiToken
    bielikModel       = $BielikModel
    embeddingProvider = $EmbeddingProvider
    encKeyHint        = 'zapisz CSM_MAP_ENCRYPTION_KEY bezpiecznie — bez niego dane sa niedostepne po odbudowie serwera'
    createdAt         = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
}
$result | ConvertTo-Json | Set-Content $OutputFile -Encoding UTF8

Write-Host ''
Write-Host '=========================================================' -ForegroundColor Green
Write-Host ' CSM VPS gotowy!' -ForegroundColor Green
Write-Host '=========================================================' -ForegroundColor Green
Write-Host " URL addinu (do manifestu Worda): $addinBaseUrl" -ForegroundColor Cyan
Write-Host " URL API:                          $apiBaseUrl" -ForegroundColor Cyan
Write-Host " Token API (CSM_API_TOKEN):        $apiToken" -ForegroundColor Yellow
Write-Host " Wynik zapisany w:                 $OutputFile" -ForegroundColor Gray
Write-Host ''
Write-Host ' WAZNE: Zapisz token API w bezpiecznym miejscu.' -ForegroundColor Red
Write-Host ' Bez tokena addin nie polacy sie z serwerem.' -ForegroundColor Red
Write-Host '=========================================================`n' -ForegroundColor Green
