; IrisClick Desktop installer (Inno Setup 6). Built by packaging\build.ps1, which passes
; /DAppVersion and /DSourceDir (the app folder). Installs for the current user only: no
; admin rights, and the app's storage folder stays writable. No secrets are inside.

#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "out\IrisClick-Desktop"
#endif

[Setup]
AppId={{6F2C7B1E-5A43-4C1D-9E8B-2D7A4F3C9B10}
AppName=IrisClick Desktop
AppVersion={#AppVersion}
AppPublisher=IrisClick (PDAO Lapu-Lapu City)
AppComments=Hands-free computer access with a webcam. Works with the IrisClick website.
DefaultDirName={localappdata}\Programs\IrisClick Desktop
DefaultGroupName=IrisClick
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=IrisClick-Desktop-Setup
SetupIconFile={#SourceDir}\irisclick.ico
UninstallDisplayIcon={app}\irisclick.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no

[Tasks]
Name: "desktopicon"; Description: "Put an IrisClick shortcut on the desktop"
Name: "startup"; Description: "Start IrisClick when Windows starts (recommended for hands-free use)"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\IrisClick"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\server\launch_irisclick.pyw"""; WorkingDir: "{app}\server"; IconFilename: "{app}\irisclick.ico"
Name: "{autodesktop}\IrisClick"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\server\launch_irisclick.pyw"""; WorkingDir: "{app}\server"; IconFilename: "{app}\irisclick.ico"; Tasks: desktopicon
Name: "{autoprograms}\Stop IrisClick"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\server\launch_irisclick.pyw"" --stop"; WorkingDir: "{app}\server"; IconFilename: "{app}\irisclick.ico"

[Registry]
; Same entry as the tray's "Start with Windows" (app/launcher.py RUN_KEY / RUN_NAME).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "IrisClick Desktop"; ValueData: """{app}\runtime\pythonw.exe"" ""{app}\server\launch_irisclick.pyw"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\server\launch_irisclick.pyw"""; WorkingDir: "{app}\server"; Description: "Start IrisClick now"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{app}\runtime\python.exe"; Parameters: """{app}\server\launch_irisclick.pyw"" --stop"; WorkingDir: "{app}\server"; Flags: runhidden waituntilterminated; RunOnceId: "StopIrisClick"

[UninstallDelete]
; Files the app made while running (logs, local database copy, sync state). Calibration
; profiles in storage\calibration_profiles are removed too: they belong to this install.
Type: filesandordirs; Name: "{app}\server\app\storage"
Type: files; Name: "{app}\server\irisclick.db"

[Code]
// Stop a running copy before files are replaced (upgrade or reinstall).
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\runtime\python.exe')) then
    Exec(ExpandConstant('{app}\runtime\python.exe'),
         '"' + ExpandConstant('{app}\server\launch_irisclick.pyw') + '" --stop',
         ExpandConstant('{app}\server'), SW_HIDE, ewWaitUntilTerminated, Code);
end;
