; Inno Setup 6 script: wraps the PyInstaller onedir folder (dist\SubScript\) into a
; per-user installer  ->  installer\Output\SubScript-Setup-<version>.exe
;
; Build:  scripts\build_installer.bat   (finds ISCC.exe, sets SUBSCRIPT_VERSION)
; Needs:  Inno Setup 6.3+  (winget install JRSoftware.InnoSetup)
;
; Design notes
; - Installs under %LOCALAPPDATA%\Programs\SubScript with PrivilegesRequired=lowest.
;   The app writes config.yaml, out\, assets\ and token.json BESIDE the exe, so the
;   install folder must stay writable without admin rights.
; - config.yaml / out\ / secrets are never shipped or overwritten: the app creates
;   config.yaml from config.example.yaml on first launch.
; - ffmpeg.exe / ffprobe.exe are included only if they sit in dist\SubScript\ at
;   build time (scripts\build_windows.bat copies them from PATH when it can).

#define MyAppName "SubScript"
#define MyAppPublisher "SensoredRooster"
#define MyAppURL "https://github.com/SensoredRooster/sub-script"
#define MyAppExeName "SubScript.exe"
#define DistDir "..\dist\SubScript"

#define VerEnv GetEnv("SUBSCRIPT_VERSION")
#if VerEnv == ""
  #define MyAppVersion "0.1.0"
#else
  #define MyAppVersion VerEnv
#endif

#ifndef FileExists(DistDir + "\" + MyAppExeName)
  #error dist\SubScript\SubScript.exe not found - run scripts\build_windows.bat first
#endif

[Setup]
AppId={{B7E3C6E0-5B7A-4D0E-9C1F-2F4A8E6D3B21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=SubScript-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Whole onedir bundle. Exclude anything user-specific that a dev machine may have left there.
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; \
  Excludes: "config.yaml,\out\*,token.json,credentials.json,client_secret*.json,.env,*.log"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "Clip, brand, review, publish"
Name: "{group}\Open SubScript folder"; Filename: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Runtime-created folders that are safe to remove. Clips in out\ are deliberately KEPT.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not FileExists(ExpandConstant('{app}\ffmpeg.exe')) then
      MsgBox('ffmpeg.exe was not found next to SubScript.exe.' + #13#10 + #13#10 +
             'Clipping needs it. Copy ffmpeg.exe (and ffprobe.exe) from a Windows ffmpeg zip into:' + #13#10 +
             ExpandConstant('{app}') + #13#10 + #13#10 +
             'See FFMPEG_BESIDE_APP.txt in that folder for download links.',
             mbInformation, MB_OK);
  end;
end;
