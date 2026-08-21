#define MyAppName "CSM for Word"
#define MyAppVersion "1.6"
#define MyAppPublisher "Kantorowski x Glab"
#define SourceDir AddBackslash(SourcePath) + ".."

[Setup]
AppId={{B1F6324D-6ED4-4C45-A9E5-C5A042200001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={sd}\CSM
DefaultGroupName=CSM for Word
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename=CSM-Setup-v{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\assets\csm.ico
SetupLogging=yes
LicenseFile={#SourceDir}\LICENSE.txt
WizardImageFile={#SourceDir}\assets\wizard-banner.bmp
WizardSmallImageFile={#SourceDir}\assets\wizard-small.bmp

[Languages]
Name: "polish"; MessagesFile: "compiler:Languages\Polish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "addin\csm-token.js,.git\*,.github\*,.pytest_cache\*,__pycache__\*,node_modules\*,.venv\*,installer\output\*,backups\*,sessions\*,maps\*,logs\*,runtime\*"

[Icons]
Name: "{group}\CSM - uruchom"; Filename: "{app}\tools\start-claude-safe-mode.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\assets\csm.ico"
Name: "{group}\CSM - zatrzymaj"; Filename: "{app}\tools\stop-claude-safe-mode.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\assets\csm.ico"
Name: "{group}\CSM - diagnoza"; Filename: "{app}\tools\CSM-DIAGNOZA.cmd"; WorkingDir: "{app}"; IconFilename: "{app}\assets\csm.ico"
Name: "{group}\Odinstaluj CSM"; Filename: "{uninstallexe}"; IconFilename: "{app}\assets\csm.ico"

[Run]
; Krok 1 (admin): Utwórz udział SMB zanim install-csm.ps1 będzie go szukać — bez UAC podczas instalacji
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install-share-admin.ps1"" -InstallDir ""{app}"""; StatusMsg: "Konfiguruje udzial Word (SMB)..."; Flags: runhidden waituntilterminated
; Krok 2 (uzytkownik): Python, cert, TrustedCatalog, autostart, start CSM
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install-csm.ps1"" -InstallDir ""{app}"" -OriginalSourceRoot ""{app}"" -FromInstaller -AcceptLicense{code:GetVpsInstallParams}{code:GetBielikModelParam}"; StatusMsg: "Konfiguruje CSM..."; Flags: runhidden waituntilterminated runasoriginaluser
; Krok 3 (admin): Skopiuj cert localhost do LocalMachine\Root — wymagane dla WebView2 w Word
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install-cert-machine.ps1"" -CertDir ""{localappdata}\.office-addin-dev-certs"""; StatusMsg: "Instaluje certyfikat HTTPS dla Word..."; Flags: runhidden waituntilterminated

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\uninstall-csm.ps1"" -InstallDir ""{app}"""; Flags: runhidden waituntilterminated; RunOnceId: "CSMUninstall"

[Code]
// CSM v1.0 - Progress monitor
// setup-once.ps1 writes %TEMP%\CSM-progress.json every few seconds.
// JSON keys: pct (0-100 int), phase (string), detail (string), state (string)
// This code reads the file every 500ms via SetTimer and updates the wizard UI.

// Win32 API - timer (user32.dll)
function SetTimer(Wnd: LongWord; IDEvent: LongWord; Elapse: LongWord;
                  TimerFunc: LongWord): LongWord;
  external 'SetTimer@user32.dll stdcall';
function KillTimer(Wnd: LongWord; IDEvent: LongWord): LongWord;
  external 'KillTimer@user32.dll stdcall';

var
  // Welcome/Finished page links
  GLink1, GLink2: TNewLinkLabel;

  // Progress monitor state
  GProgressFile:   String;
  GTimerID:        LongWord;
  GLastPct:        Integer;
  GGaugeTaken:     Boolean;

  // VPS deployment page
  GVpsPage:         TWizardPage;
  GVpsRadioLocal:   TRadioButton;
  GVpsRadioHetzner: TRadioButton;
  GVpsRadioIoNos:   TRadioButton;
  GVpsRadioCustom:  TRadioButton;
  GVpsDetailsPanel: TPanel;
  GVpsApiKeyEdit:   TEdit;
  GVpsDomainEdit:   TEdit;
  GVpsRegionCombo:  TComboBox;

  // Bielik model selection page
  GBielikPage:        TWizardPage;
  GBielikRadio1B5:    TRadioButton;
  GBielikRadio4B5:    TRadioButton;
  GBielikRadio7B:     TRadioButton;
  GBielikRadio11B:    TRadioButton;

  // Extra labels added below the progress gauge
  GPhaseLabel:     TLabel;
  GDetailLabel:    TLabel;
  GCompBarLabel:   TLabel;
  GCompBar:        TNewProgressBar;
  GCompTick:       Integer;


// --- VPS page helpers -------------------------------------------------------

procedure UpdateVpsDetailsVisibility(Sender: TObject);
var
  Show: Boolean;
begin
  Show := GVpsRadioHetzner.Checked or GVpsRadioIoNos.Checked;
  GVpsDetailsPanel.Visible := Show;
  if Show and Assigned(GVpsRegionCombo) then begin
    GVpsRegionCombo.Items.Clear;
    if GVpsRadioIoNos.Checked then begin
      GVpsRegionCombo.Items.Add('de   — Frankfurt, Niemcy (IONOS, domyslny)');
      GVpsRegionCombo.Items.Add('fr   — Paryż, Francja (IONOS)');
    end else begin
      GVpsRegionCombo.Items.Add('fsn1 — Falkenstein, Niemcy (domyslny)');
      GVpsRegionCombo.Items.Add('nbg1 — Norymberga, Niemcy');
      GVpsRegionCombo.Items.Add('hel1 — Helsinki, Finlandia');
    end;
    GVpsRegionCombo.ItemIndex := 0;
  end;
end;

function NormalizeRegion(Value: String): String;
var
  S: String;
  P: Integer;
begin
  S := Trim(Value);
  P := Pos(' ', S);
  if P > 0 then S := Copy(S, 1, P - 1);
  Result := Trim(S);
end;

function GetVpsInstallParams(Param: String): String;
var
  Provider, ApiKey, Domain, Region: String;
begin
  Result := '';
  if GVpsRadioLocal.Checked or GVpsRadioCustom.Checked then Exit;

  if GVpsRadioHetzner.Checked then Provider := 'hetzner'
  else Provider := 'ionos';

  ApiKey := GVpsApiKeyEdit.Text;
  Domain := GVpsDomainEdit.Text;
  Region := NormalizeRegion(GVpsRegionCombo.Text);
  if Region = '' then begin
    if Provider = 'hetzner' then Region := 'fsn1' else Region := 'de';
  end;

  // Parametry przekazane do install-csm.ps1 ktory wywolje provision-vps.ps1
  Result := ' -VpsProvider ' + Provider +
            ' -VpsApiKey "' + ApiKey + '"' +
            ' -VpsDomain "' + Domain + '"' +
            ' -VpsRegion "' + Region + '"';
end;

function VpsPageNextAllowed(): Boolean;
var
  ApiKey, Domain: String;
begin
  Result := True;
  if GVpsRadioLocal.Checked or GVpsRadioCustom.Checked then Exit;
  ApiKey := Trim(GVpsApiKeyEdit.Text);
  Domain := Trim(GVpsDomainEdit.Text);
  if ApiKey = '' then begin
    MsgBox('Podaj klucz API dostawcy VPS.', mbError, MB_OK);
    Result := False; Exit;
  end;
  if Domain = '' then begin
    MsgBox('Podaj domene dla serwera CSM (np. csm.kancelaria.pl).' + #13#10 +
           'Domena musi wskazywac na adres IP VPS po utworzeniu.', mbError, MB_OK);
    Result := False; Exit;
  end;
  if Pos('.', Domain) = 0 then begin
    MsgBox('Domena musi byc pelna (np. csm.kancelaria.pl), nie sama nazwa.', mbError, MB_OK);
    Result := False; Exit;
  end;
end;

procedure CreateVpsWizardPage();
var
  PageDesc: TLabel;
  LblProvider, LblApiKey, LblDomain, LblRegion, LblInfo: TLabel;
  Y: Integer;
begin
  GVpsPage := CreateCustomPage(wpLicense,
    'Tryb wdrozenia CSM',
    'Wybierz gdzie ma dzialac serwer CSM');

  // Opis ogolny
  PageDesc := TLabel.Create(GVpsPage);
  PageDesc.Parent := GVpsPage.Surface;
  PageDesc.Left := 0; PageDesc.Top := 0;
  PageDesc.Width := GVpsPage.SurfaceWidth;
  PageDesc.Height := 32;
  PageDesc.AutoSize := False;
  PageDesc.WordWrap := True;
  PageDesc.Caption := 'CSM moze dzialac na Twoim komputerze (lokalnie) lub na serwerze VPS w UE ' +
                      '(Niemcy/Finlandia). Tryb VPS spelnia wymogi RODO i tajemnicy zawodowej.';

  Y := 38;
  LblProvider := TLabel.Create(GVpsPage);
  LblProvider.Parent := GVpsPage.Surface;
  LblProvider.Left := 0; LblProvider.Top := Y;
  LblProvider.Caption := 'Tryb wdrozenia:';
  LblProvider.Font.Style := [fsBold];
  Y := Y + 22;

  // Opcja 1: Lokalnie (domyslna)
  GVpsRadioLocal := TRadioButton.Create(GVpsPage);
  GVpsRadioLocal.Parent := GVpsPage.Surface;
  GVpsRadioLocal.Left := 8; GVpsRadioLocal.Top := Y;
  GVpsRadioLocal.Width := GVpsPage.SurfaceWidth - 8; GVpsRadioLocal.Height := 22;
  GVpsRadioLocal.Caption := 'Lokalnie (domyslnie) — serwer dziala na tym komputerze';
  GVpsRadioLocal.Checked := True;
  GVpsRadioLocal.OnClick := @UpdateVpsDetailsVisibility;
  Y := Y + 26;

  // Opcja 2: Hetzner
  GVpsRadioHetzner := TRadioButton.Create(GVpsPage);
  GVpsRadioHetzner.Parent := GVpsPage.Surface;
  GVpsRadioHetzner.Left := 8; GVpsRadioHetzner.Top := Y;
  GVpsRadioHetzner.Width := GVpsPage.SurfaceWidth - 8; GVpsRadioHetzner.Height := 22;
  GVpsRadioHetzner.Caption := 'Hetzner Cloud (Niemcy, ~4,49 EUR/mies.) — ISO 27001 + BSI C5, dane w UE';
  GVpsRadioHetzner.OnClick := @UpdateVpsDetailsVisibility;
  Y := Y + 26;

  // Opcja 3: IONOS
  GVpsRadioIoNos := TRadioButton.Create(GVpsPage);
  GVpsRadioIoNos.Parent := GVpsPage.Surface;
  GVpsRadioIoNos.Left := 8; GVpsRadioIoNos.Top := Y;
  GVpsRadioIoNos.Width := GVpsPage.SurfaceWidth - 8; GVpsRadioIoNos.Height := 22;
  GVpsRadioIoNos.Caption := 'IONOS Cloud (Niemcy, ~9 EUR/mies.) — ISO 27001 + BSI C5, dane w UE';
  GVpsRadioIoNos.OnClick := @UpdateVpsDetailsVisibility;
  Y := Y + 26;

  // Opcja 4: Wlasny
  GVpsRadioCustom := TRadioButton.Create(GVpsPage);
  GVpsRadioCustom.Parent := GVpsPage.Surface;
  GVpsRadioCustom.Left := 8; GVpsRadioCustom.Top := Y;
  GVpsRadioCustom.Width := GVpsPage.SurfaceWidth - 8; GVpsRadioCustom.Height := 22;
  GVpsRadioCustom.Caption := 'Wlasny VPS (konfiguracja recznie po instalacji przez tools\provision-vps.ps1)';
  GVpsRadioCustom.OnClick := @UpdateVpsDetailsVisibility;
  Y := Y + 34;

  // Panel z polami dla Hetzner/IONOS (ukryty domyslnie)
  GVpsDetailsPanel := TPanel.Create(GVpsPage);
  GVpsDetailsPanel.Parent := GVpsPage.Surface;
  GVpsDetailsPanel.Left := 0; GVpsDetailsPanel.Top := Y;
  GVpsDetailsPanel.Width := GVpsPage.SurfaceWidth;
  GVpsDetailsPanel.Height := 130;
  GVpsDetailsPanel.BevelOuter := bvNone;
  GVpsDetailsPanel.Visible := False;

  // API Key
  LblApiKey := TLabel.Create(GVpsDetailsPanel);
  LblApiKey.Parent := GVpsDetailsPanel;
  LblApiKey.Left := 0; LblApiKey.Top := 4; LblApiKey.Caption := 'Klucz API dostawcy:';
  GVpsApiKeyEdit := TEdit.Create(GVpsDetailsPanel);
  GVpsApiKeyEdit.Parent := GVpsDetailsPanel;
  GVpsApiKeyEdit.Left := 140; GVpsApiKeyEdit.Top := 0;
  GVpsApiKeyEdit.Width := GVpsPage.SurfaceWidth - 150; GVpsApiKeyEdit.Height := 22;
  GVpsApiKeyEdit.PasswordChar := '*';

  // Domain
  LblDomain := TLabel.Create(GVpsDetailsPanel);
  LblDomain.Parent := GVpsDetailsPanel;
  LblDomain.Left := 0; LblDomain.Top := 32; LblDomain.Caption := 'Domena (np. csm.firma.pl):';
  GVpsDomainEdit := TEdit.Create(GVpsDetailsPanel);
  GVpsDomainEdit.Parent := GVpsDetailsPanel;
  GVpsDomainEdit.Left := 140; GVpsDomainEdit.Top := 28;
  GVpsDomainEdit.Width := GVpsPage.SurfaceWidth - 150; GVpsDomainEdit.Height := 22;

  // Region
  LblRegion := TLabel.Create(GVpsDetailsPanel);
  LblRegion.Parent := GVpsDetailsPanel;
  LblRegion.Left := 0; LblRegion.Top := 60; LblRegion.Caption := 'Lokalizacja serwera:';
  GVpsRegionCombo := TComboBox.Create(GVpsDetailsPanel);
  GVpsRegionCombo.Parent := GVpsDetailsPanel;
  GVpsRegionCombo.Left := 140; GVpsRegionCombo.Top := 56;
  GVpsRegionCombo.Width := 260; GVpsRegionCombo.Style := csDropDownList;
  GVpsRegionCombo.Items.Add('fsn1 — Falkenstein, Niemcy (domyslny)');
  GVpsRegionCombo.Items.Add('nbg1 — Norymberga, Niemcy');
  GVpsRegionCombo.Items.Add('hel1 — Helsinki, Finlandia');
  GVpsRegionCombo.ItemIndex := 0;

  // Informacja o RODO
  LblInfo := TLabel.Create(GVpsDetailsPanel);
  LblInfo.Parent := GVpsDetailsPanel;
  LblInfo.Left := 0; LblInfo.Top := 92;
  LblInfo.Width := GVpsPage.SurfaceWidth; LblInfo.AutoSize := False;
  LblInfo.WordWrap := True; LblInfo.Height := 34;
  LblInfo.Font.Color := clGray;
  LblInfo.Caption := 'Installer automatycznie utworzy VPS, wgra serwer i wygeneruje certyfikat HTTPS. ' +
                     'Bedziesz musial skonfigurowac rekord DNS (A) po podaniu adresu IP.';
end;

// Wykrywa juz zainstalowany model Bielik przez "ollama list".
// Zwraca '1.5B' / '4.5B' / '7B' / '11B' gdy rozpoznano rozmiar,
// 'UNKNOWN' gdy Bielik jest ale nie rozpoznano rozmiaru,
// pusty string gdy Ollama nie jest zainstalowana lub brak modelu Bielik.
function DetectInstalledBielikModel(): String;
var
  ResultCode: Integer;
  TmpFile: String;
  Lines: TArrayOfString;
  I: Integer;
  Line: String;
begin
  Result := '';
  TmpFile := ExpandConstant('{tmp}\csm_ollama_list.txt');
  if Exec(ExpandConstant('{cmd}'), '/C ollama list > "' + TmpFile + '" 2>&1',
     '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if (ResultCode = 0) and LoadStringsFromFile(TmpFile, Lines) then
    begin
      for I := 0 to GetArrayLength(Lines) - 1 do
      begin
        Line := Lowercase(Lines[I]);
        if Pos('bielik', Line) > 0 then
        begin
          if Pos('11b', Line) > 0 then begin Result := '11B'; Break; end;
          if Pos('4.5b', Line) > 0 then begin Result := '4.5B'; Break; end;
          if Pos('7b', Line) > 0 then begin Result := '7B'; Break; end;
          if Pos('1.5b', Line) > 0 then begin Result := '1.5B'; Break; end;
          Result := 'UNKNOWN';
          Break;
        end;
      end;
    end;
  end;
  if FileExists(TmpFile) then DeleteFile(TmpFile);
end;

function GetBielikModelParam(Param: String): String;
begin
  if GBielikRadio1B5.Checked then
    Result := ' -BielikModel "hf.co/speakleash/Bielik-1.5B-v3.0-Instruct-GGUF:Q8_0"'
  else if GBielikRadio4B5.Checked then
    Result := ' -BielikModel "hf.co/speakleash/Bielik-4.5B-v3.0-Instruct-GGUF:Q8_0"'
  else if GBielikRadio11B.Checked then
    Result := ' -BielikModel "hf.co/speakleash/Bielik-11B-v3.0-Instruct-GGUF:Q4_K_M"'
  else
    Result := ' -BielikModel "hf.co/speakleash/Bielik-Minitron-7B-v3.0-Instruct-GGUF:Q4_K_M"';
end;

procedure CreateBielikWizardPage();
var
  PageDesc, LblModel, LblInfo1, LblInfo4, LblInfo7, LblInfo11, LblRec, LblDetected: TLabel;
  Y: Integer;
  Detected: String;
begin
  GBielikPage := CreateCustomPage(GVpsPage.ID,
    'Model AI - Bielik',
    'Wybierz wersje modelu Bielik do analizy dokumentow');

  PageDesc := TLabel.Create(GBielikPage);
  PageDesc.Parent := GBielikPage.Surface;
  PageDesc.Left := 0; PageDesc.Top := 0;
  PageDesc.Width := GBielikPage.SurfaceWidth;
  PageDesc.Height := 38;
  PageDesc.AutoSize := False;
  PageDesc.WordWrap := True;
  PageDesc.Caption := 'Model Bielik wykrywa dane osobowe (PII) w dokumentach. ' +
                      'Wiekszy model = lepsza jakosc, ale wymaga wiecej RAM. ' +
                      'Dla VPS Hetzner cx33 (~6,49 EUR/mies.) polecamy wersje 11B.';
  Y := 44;

  // Autodetekcja juz zainstalowanego modelu (uruchamiana raz, przy tworzeniu strony).
  // Nie ukrywa strony — informuje uzytkownika i ustawia wstepny wybor,
  // ktory uzytkownik moze zmienic.
  Detected := DetectInstalledBielikModel();
  if Detected <> '' then
  begin
    LblDetected := TLabel.Create(GBielikPage);
    LblDetected.Parent := GBielikPage.Surface;
    LblDetected.Left := 0; LblDetected.Top := Y;
    LblDetected.Width := GBielikPage.SurfaceWidth; LblDetected.AutoSize := False;
    LblDetected.WordWrap := True; LblDetected.Height := 34;
    if Detected = 'UNKNOWN' then
    begin
      LblDetected.Font.Color := clNavy;
      LblDetected.Caption := 'Wykryto zainstalowany model Bielik na tym komputerze, ale nie rozpoznano jego rozmiaru. ' +
                             'Pozostawiono domyslny wybor ponizej — mozesz go zmienic.';
    end
    else
    begin
      LblDetected.Font.Style := [fsBold];
      LblDetected.Font.Color := clGreen;
      LblDetected.Caption := 'Wykryto juz zainstalowany model Bielik ' + Detected + ' na tym komputerze. ' +
                             'Mozesz kliknac Dalej, aby go zachowac, albo wybrac inny rozmiar ponizej.';
    end;
    Y := Y + 40;
  end;

  LblModel := TLabel.Create(GBielikPage);
  LblModel.Parent := GBielikPage.Surface;
  LblModel.Left := 0; LblModel.Top := Y;
  LblModel.Caption := 'Wersja modelu Bielik:';
  LblModel.Font.Style := [fsBold];
  Y := Y + 22;

  GBielikRadio1B5 := TRadioButton.Create(GBielikPage);
  GBielikRadio1B5.Parent := GBielikPage.Surface;
  GBielikRadio1B5.Left := 8; GBielikRadio1B5.Top := Y;
  GBielikRadio1B5.Width := GBielikPage.SurfaceWidth - 8; GBielikRadio1B5.Height := 20;
  GBielikRadio1B5.Caption := 'Bielik 1.5B  —  min. 4 GB RAM  |  jakosc: podstawowa  |  VPS cx23 (~3,99 EUR) / slabszy laptop';
  Y := Y + 22;
  LblInfo1 := TLabel.Create(GBielikPage);
  LblInfo1.Parent := GBielikPage.Surface;
  LblInfo1.Left := 26; LblInfo1.Top := Y; LblInfo1.Font.Color := clGray;
  LblInfo1.Caption := 'Prosty detektor PII, szybka praca, najmniejsze wymagania sprzetowe.';
  Y := Y + 24;

  GBielikRadio4B5 := TRadioButton.Create(GBielikPage);
  GBielikRadio4B5.Parent := GBielikPage.Surface;
  GBielikRadio4B5.Left := 8; GBielikRadio4B5.Top := Y;
  GBielikRadio4B5.Width := GBielikPage.SurfaceWidth - 8; GBielikRadio4B5.Height := 20;
  GBielikRadio4B5.Caption := 'Bielik 4.5B  —  min. 6 GB RAM  |  jakosc: posrednia  |  VPS cx33 (~6,49 EUR/mies.)';
  Y := Y + 22;
  LblInfo4 := TLabel.Create(GBielikPage);
  LblInfo4.Parent := GBielikPage.Surface;
  LblInfo4.Left := 26; LblInfo4.Top := Y; LblInfo4.Font.Color := clGray;
  LblInfo4.Caption := 'Model natywny 4,6 mld parametrow. Jakosc posrednia miedzy 1.5B a 7B Minitron.';
  Y := Y + 24;

  GBielikRadio7B := TRadioButton.Create(GBielikPage);
  GBielikRadio7B.Parent := GBielikPage.Surface;
  GBielikRadio7B.Left := 8; GBielikRadio7B.Top := Y;
  GBielikRadio7B.Width := GBielikPage.SurfaceWidth - 8; GBielikRadio7B.Height := 20;
  GBielikRadio7B.Caption := 'Bielik 7B Minitron (domyslny)  —  min. 8 GB RAM  |  jakosc: dobra  |  VPS cx33 / laptop 16 GB';
  GBielikRadio7B.Checked := True;
  Y := Y + 22;
  LblInfo7 := TLabel.Create(GBielikPage);
  LblInfo7.Parent := GBielikPage.Surface;
  LblInfo7.Left := 26; LblInfo7.Top := Y; LblInfo7.Font.Color := clGray;
  LblInfo7.Caption := 'Dobry balans jakosci i szybkosci. Zalecany dla instalacji lokalnej na mocniejszym sprzecie.';
  Y := Y + 24;

  GBielikRadio11B := TRadioButton.Create(GBielikPage);
  GBielikRadio11B.Parent := GBielikPage.Surface;
  GBielikRadio11B.Left := 8; GBielikRadio11B.Top := Y;
  GBielikRadio11B.Width := GBielikPage.SurfaceWidth - 8; GBielikRadio11B.Height := 20;
  GBielikRadio11B.Caption := 'Bielik 11B  —  min. 12 GB RAM  |  jakosc: doskonala  |  VPS cx33 (~6,49 EUR/mies.)';
  Y := Y + 22;
  LblInfo11 := TLabel.Create(GBielikPage);
  LblInfo11.Parent := GBielikPage.Surface;
  LblInfo11.Left := 26; LblInfo11.Top := Y; LblInfo11.Font.Color := clGray;
  LblInfo11.Caption := 'Najlepsza jakosc dla polskich dokumentow prawnych. Zalecany dla VPS kancelarii.';
  Y := Y + 30;

  // Jesli wykryto konkretny rozmiar, zaznacz odpowiadajacy radio zamiast domyslnego 7B.
  // Radio w tym samym rodzicu tworza grupe — ustawienie .Checked := True
  // automatycznie odznacza pozostale.
  if Detected = '1.5B' then
    GBielikRadio1B5.Checked := True
  else if Detected = '4.5B' then
    GBielikRadio4B5.Checked := True
  else if Detected = '7B' then
    GBielikRadio7B.Checked := True
  else if Detected = '11B' then
    GBielikRadio11B.Checked := True;

  LblRec := TLabel.Create(GBielikPage);
  LblRec.Parent := GBielikPage.Surface;
  LblRec.Left := 0; LblRec.Top := Y;
  LblRec.Width := GBielikPage.SurfaceWidth; LblRec.AutoSize := False;
  LblRec.WordWrap := True; LblRec.Height := 36;
  LblRec.Font.Color := clNavy;
  LblRec.Caption := 'Wskazowka: dla VPS Hetzner cx33 wybierz 11B. ' +
                    'Dla instalacji lokalnej na laptopie 8-16 GB wybierz 7B (domyslny).';
end;

// --- Tiny JSON field readers (no stdlib needed) --------------------------

function JStr(const J, Key: String): String;
var
  p, q: Integer;
begin
  Result := '';
  p := Pos('"' + Key + '"', J);
  if p = 0 then Exit;
  p := p + Length(Key) + 2;
  while (p <= Length(J)) and (J[p] <> '"') do p := p + 1;
  if p > Length(J) then Exit;
  p := p + 1;
  q := p;
  while (q <= Length(J)) and (J[q] <> '"') do begin
    if J[q] = '\' then q := q + 1;
    q := q + 1;
  end;
  Result := Copy(J, p, q - p);
end;

function JInt(const J, Key: String; Def: Integer): Integer;
var
  p: Integer;
  s: String;
  c: Char;
begin
  Result := Def;
  p := Pos('"' + Key + '"', J);
  if p = 0 then Exit;
  p := p + Length(Key) + 2;
  while (p <= Length(J)) and ((J[p] = ' ') or (J[p] = ':')) do p := p + 1;
  s := '';
  while p <= Length(J) do begin
    c := J[p];
    if (c >= '0') and (c <= '9') then s := s + c
    else if s <> '' then Break;
    p := p + 1;
  end;
  if s <> '' then Result := StrToIntDef(s, Def);
end;

function StatePrefix(const St: String): String;
begin
  if      St = 'checking'    then Result := '[?] '
  else if St = 'downloading' then Result := '[v] '
  else if St = 'installing'  then Result := '[*] '
  else if St = 'done'        then Result := '[ok] '
  else if St = 'error'       then Result := '[!] '
  else Result := '';
end;


// --- Timer callback (called from Windows message loop) -------------------

procedure ProgressTimerProc(hWnd: LongWord; uMsg: LongWord;
                             idEvent: LongWord; dwTime: LongWord);
var
  RawContent: AnsiString;
  Content, Phase, Detail, St: String;
  Pct: Integer;
begin
  if not FileExists(GProgressFile) then Exit;
  if not LoadStringFromFile(GProgressFile, RawContent) then Exit;
  Content := String(RawContent);
  if Content = '' then Exit;

  Pct    := JInt(Content, 'pct', -1);
  Phase  := JStr(Content, 'phase');
  Detail := JStr(Content, 'detail');
  St     := JStr(Content, 'state');

  if (Pct < 0) or (Pct > 100) then Exit;

  // Take control of the main progress gauge on first valid read
  if not GGaugeTaken then begin
    WizardForm.ProgressGauge.Style := npbstNormal;
    WizardForm.ProgressGauge.Min   := 0;
    WizardForm.ProgressGauge.Max   := 100;
    GGaugeTaken := True;
  end;

  // Advance main bar (never go backwards)
  if Pct > GLastPct then begin
    WizardForm.ProgressGauge.Position := Pct;
    GLastPct := Pct;
  end;

  // Phase label (bold - which component)
  if (GPhaseLabel <> nil) and (Phase <> '') then
    GPhaseLabel.Caption := Phase;

  // Detail label (what is happening right now)
  if GDetailLabel <> nil then begin
    if Detail <> '' then
      GDetailLabel.Caption := StatePrefix(St) + Detail
    else if Phase <> '' then
      GDetailLabel.Caption := StatePrefix(St) + Phase;
  end;

  // Secondary bar - animated while downloading or installing
  if GCompBar <> nil then begin
    if (St = 'downloading') or (St = 'installing') then begin
      if not GCompBar.Visible then begin
        GCompBar.Visible      := True;
        GCompBarLabel.Visible := True;
        GCompTick := 0;
      end;
      GCompTick := GCompTick + 5;
      if GCompTick > 100 then GCompTick := 0;
      GCompBar.Position := GCompTick;
      if St = 'downloading' then
        GCompBarLabel.Caption := 'Pobieranie: ' + Phase
      else
        GCompBarLabel.Caption := 'Instalowanie: ' + Phase;
    end else begin
      GCompBar.Visible      := False;
      GCompBarLabel.Visible := False;
    end;
  end;
end;


// --- Build extra controls positioned below the main progress gauge -------

procedure BuildProgressUi();
var
  GX, GY, GW, GH, Y: Integer;
begin
  GX := WizardForm.ProgressGauge.Left;
  GY := WizardForm.ProgressGauge.Top;
  GW := WizardForm.ProgressGauge.Width;
  GH := WizardForm.ProgressGauge.Height;
  Y  := GY + GH + ScaleY(10);

  // Phase label (bold, component name)
  GPhaseLabel := TLabel.Create(WizardForm);
  GPhaseLabel.Parent     := WizardForm;
  GPhaseLabel.Left       := GX;
  GPhaseLabel.Top        := Y;
  GPhaseLabel.Width      := GW;
  GPhaseLabel.AutoSize   := False;
  GPhaseLabel.Height     := ScaleY(16);
  GPhaseLabel.Font.Style := [fsBold];
  GPhaseLabel.Caption    := 'Przygotowywanie...';
  Y := Y + ScaleY(20);

  // Detail label
  GDetailLabel := TLabel.Create(WizardForm);
  GDetailLabel.Parent   := WizardForm;
  GDetailLabel.Left     := GX;
  GDetailLabel.Top      := Y;
  GDetailLabel.Width    := GW;
  GDetailLabel.AutoSize := False;
  GDetailLabel.Height   := ScaleY(28);
  GDetailLabel.WordWrap := True;
  GDetailLabel.Caption  := '';
  Y := Y + ScaleY(34);

  // Component bar label (only when downloading/installing)
  GCompBarLabel := TLabel.Create(WizardForm);
  GCompBarLabel.Parent   := WizardForm;
  GCompBarLabel.Left     := GX;
  GCompBarLabel.Top      := Y;
  GCompBarLabel.Width    := GW;
  GCompBarLabel.AutoSize := False;
  GCompBarLabel.Height   := ScaleY(14);
  GCompBarLabel.Caption  := '';
  GCompBarLabel.Visible  := False;
  Y := Y + ScaleY(16);

  // Component progress bar (animated indicator for long downloads)
  GCompBar := TNewProgressBar.Create(WizardForm);
  GCompBar.Parent   := WizardForm;
  GCompBar.Left     := GX;
  GCompBar.Top      := Y;
  GCompBar.Width    := GW;
  GCompBar.Height   := ScaleY(8);
  GCompBar.Min      := 0;
  GCompBar.Max      := 100;
  GCompBar.Position := 0;
  GCompBar.Style    := npbstNormal;
  GCompBar.Visible  := False;
  GCompTick := 0;
end;


// --- Start / stop the progress monitor -----------------------------------

procedure StartProgressMonitor();
begin
  GProgressFile := GetEnv('TEMP') + '\CSM-progress.json';
  GLastPct      := 0;
  GGaugeTaken   := False;

  BuildProgressUi();

  GTimerID := SetTimer(0, 1, 500, CreateCallback(@ProgressTimerProc));
end;

procedure StopProgressMonitor();
begin
  if GTimerID <> 0 then begin
    KillTimer(0, GTimerID);
    GTimerID := 0;
  end;
  if GGaugeTaken then
    WizardForm.ProgressGauge.Position := 100;
end;


// --- Standard Inno Setup event hooks -------------------------------------

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    StartProgressMonitor()
  else if CurStep = ssDone then
    StopProgressMonitor();
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  GLink1.Visible := (CurPageID = wpWelcome) or (CurPageID = wpFinished);
  GLink2.Visible := (CurPageID = wpWelcome) or (CurPageID = wpFinished);
  if (GPhaseLabel <> nil) then
    GPhaseLabel.Visible := (CurPageID = wpInstalling);
  if (GDetailLabel <> nil) then
    GDetailLabel.Visible := (CurPageID = wpInstalling);
  if (GCompBarLabel <> nil) then
    GCompBarLabel.Visible := (CurPageID = wpInstalling) and GCompBar.Visible;
  if (GCompBar <> nil) then
    GCompBar.Visible := (CurPageID = wpInstalling) and GCompBar.Visible;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = GVpsPage.ID then
    Result := VpsPageNextAllowed();
end;

procedure InitializeWizard();
var
  BtnTop: Integer;
begin
  CreateVpsWizardPage();
  CreateBielikWizardPage();
  BtnTop := WizardForm.NextButton.Top;

  GLink1 := TNewLinkLabel.Create(WizardForm);
  GLink1.Parent  := WizardForm;
  GLink1.Caption := '<a href="https://prawodlabiznesu.eu/">prawodlabiznesu.eu</a>';
  GLink1.Left    := ScaleX(8);
  GLink1.Top     := BtnTop + ScaleY(6);
  GLink1.Width   := ScaleX(220);
  GLink1.Height  := ScaleY(18);
  GLink1.Visible := False;

  GLink2 := TNewLinkLabel.Create(WizardForm);
  GLink2.Parent  := WizardForm;
  GLink2.Caption := '<a href="https://kancelariakantorowski.pl/">kancelariakantorowski.pl</a>';
  GLink2.Left    := ScaleX(8);
  GLink2.Top     := BtnTop + ScaleY(26);
  GLink2.Width   := ScaleX(220);
  GLink2.Height  := ScaleY(18);
  GLink2.Visible := False;

  GTimerID      := 0;
  GPhaseLabel   := nil;
  GDetailLabel  := nil;
  GCompBar      := nil;
  GCompBarLabel := nil;
  GCompTick     := 0;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
end;
