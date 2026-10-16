; Inno Setup 安裝檔設定；由 packaging/build.py 傳入 AppVersion、AppAuthor
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppAuthor
  #define AppAuthor "林凌禕"
#endif

[Setup]
AppId={{7C1F4A52-5D3E-4B8A-9C61-2E0F8D9A6B13}
AppName=Saydown
AppVersion={#AppVersion}
AppVerName=Saydown {#AppVersion}
AppPublisher={#AppAuthor}
AppPublisherURL=https://github.com/allllen001/saydown
AppCopyright=© 2026 {#AppAuthor}
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Saydown
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Saydown-Setup-{#AppVersion}
SetupIconFile=..\saydown.ico
UninstallDisplayIcon={app}\Saydown.exe
Compression=lzma2/fast
SolidCompression=yes
LZMANumBlockThreads=8
DiskSpanning=no
WizardStyle=modern
CloseApplications=force
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "cht"; MessagesFile: "ChineseTraditional.isl"

[Tasks]
Name: "desktopicon"; Description: "建立桌面捷徑"
Name: "autostart"; Description: "開機自動啟動"

[Files]
Source: "..\dist\Saydown\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Saydown"; Filename: "{app}\Saydown.exe"
Name: "{userdesktop}\Saydown"; Filename: "{app}\Saydown.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Saydown"; ValueData: """{app}\Saydown.exe"" ""--guard"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Saydown.exe"; Description: "啟動 Saydown"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Saydown.exe /F"; Flags: runhidden; RunOnceId: "KillSaydown"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { 更新時先關掉執行中的 Saydown（守護程式會把主程式重開，所以全部一起關） }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Saydown.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { 系統匣勾選的開機啟動也是寫這個值，解除安裝時一併清掉 }
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Saydown');
end;
