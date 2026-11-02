; Inno Setup 6 script for the site installer. Don't run ISCC by hand: installer/build.py stages the
; app and Python into installer/build/<edition>/app and passes AppSource, AppVersion, Edition (and Sign).
#ifndef AppSource
  #error Run installer/build.py, not ISCC directly.
#endif

[Setup]
; One AppId for both editions, so a Site install can be upgraded to Enterprise (and to new versions).
AppId={{6F2B8C1E-4D7A-4B9E-9C3F-2A61D5E0B7C4}
AppName=Container Gate OCR
AppVersion={#AppVersion}
AppVerName=Container Gate OCR {#AppVersion} ({#Edition})
AppPublisher=Gate Reader
DefaultDirName={autopf}\Container Gate OCR
DefaultGroupName=Container Gate OCR
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=ContainerGateOCR-{#Edition}-{#AppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Container Gate OCR
#ifdef Sign
SignTool=gate
SignedUninstaller=yes
#endif

[InstallDelete]
; Old packages and code go before the new ones are copied; logs\ and cameras.json (site data) stay.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\src"
Type: filesandordirs; Name: "{app}\web"

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[INI]
Filename: "{app}\Gate app.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:8000"

[Icons]
Name: "{group}\Gate app"; Filename: "{app}\Gate app.url"
Name: "{autodesktop}\Gate app"; Filename: "{app}\Gate app.url"

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\autostart.ps1"" -Install"; \
  Flags: runhidden waituntilterminated; StatusMsg: "Starting the gate and opening port 8000 to the site network..."
Filename: "http://localhost:8000"; Description: "Open the Gate app"; Flags: postinstall shellexec nowait skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\autostart.ps1"" -Remove"; \
  Flags: runhidden waituntilterminated; RunOnceId: "RemoveAutostart"

[UninstallDelete]
; Code and Python only (and their __pycache__). logs\ (gate.db, photos, Excel) and cameras.json stay.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\src"
Type: files; Name: "{app}\Gate app.url"

[Code]
// Upgrading: stop the running gate first, or Windows can't replace python.exe while it runs.
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  if FileExists(ExpandConstant('{app}\autostart.ps1')) then
    Exec('powershell.exe', '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\autostart.ps1') + '" -Stop',
         '', SW_HIDE, ewWaitUntilTerminated, Code);
end;
