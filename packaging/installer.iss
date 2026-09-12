; Inno Setup script for Crypto Price Alerts.
; Compile with:  ISCC.exe packaging\installer.iss   (run by build.ps1)
; Requires the PyInstaller output in  dist\CryptoPriceAlert\  first.

#define MyAppName "Crypto Price Alerts"
#define MyAppShort "CryptoPriceAlert"
#define MyAppVersion "1.2.2"
#define MyAppPublisher "Crypto Price Alerts"
#define MyAppExe "CryptoPriceAlert.exe"

[Setup]
AppId={{9C4E7F1A-3B2D-4A6E-8F10-7D2C5E9A1B34}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppShort}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#SourcePath}\..\installer_output
OutputBaseFilename={#MyAppShort}Setup-{#MyAppVersion}
SetupIconFile={#SourcePath}\app.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon";  Description: "Create a &desktop shortcut";                       Flags: unchecked
Name: "startupicon";  Description: "Start {#MyAppName} automatically when I sign in";  Flags: unchecked

[Files]
Source: "{#SourcePath}\..\dist\CryptoPriceAlert\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}";               Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}";     Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";         Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; Same per-user Run value the app's own "Start automatically" setting writes,
; so the installer checkbox and the in-app toggle stay in sync.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "CryptoPriceAlert"; ValueData: """{app}\{#MyAppExe}"""; \
  Tasks: startupicon; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\CryptoPriceAlert');
    if DirExists(DataDir) then
      if MsgBox('Also delete your saved alerts, settings and cached data?' + #13#10 + DataDir,
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
