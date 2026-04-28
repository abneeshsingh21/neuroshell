; NeuroShell v5.0 — Windows Installer Script
; Built with Inno Setup 6.x (https://jrsoftware.org/isinfo.php)
; To compile: Download Inno Setup, open this file, press Ctrl+F9
; Output: dist\installer\NeuroShell_v5.0_Setup.exe

#define MyAppName      "NeuroShell"
#define MyAppVersion   "5.0.7"
#define MyAppPublisher "Abneesh Singh"
#define MyAppURL       "https://github.com/abneeshsingh21/neuroshell"
#define MyAppExeName   "NeuroShell.exe"
#define MyAppIcon      "assets\icon.ico"
#define DistFolder     "dist"

[Setup]
; Basic identity
AppId={{6F3A79E2-1B44-4C8A-9E4D-F0A3C2B8D7E1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases

; File layout
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=release
OutputBaseFilename=NeuroShell-windows-x64-5.0.7
SetupIconFile={#MyAppIcon}
UninstallDisplayIcon={app}\{#MyAppExeName}

; Compression (LZMA2 — best ratio for PyInstaller bundles)
Compression=lzma2/max
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Privileges — install per-user by default (no UAC prompt required)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; UI
WizardStyle=modern
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
ShowLanguageDialog=no
LicenseFile=LICENSE.txt

; Language
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

; Files to install
[Files]
; Copy the entire PyInstaller output folder
Source: "{#DistFolder}\NeuroShell.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#DistFolder}\NeuroShell-CLI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion recursesubdirs createallsubdirs

; Icons
[Icons]
; Desktop shortcut
Name: "{autodesktop}\{#MyAppName}";    FileName: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
; Start Menu shortcut
Name: "{group}\{#MyAppName}";          FileName: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\Uninstall {#MyAppName}";FileName: "{uninstallexe}"

; Optional tasks (shown on the installer page)
[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

; Registry (optional — for file associations or help links)
[Registry]
Root: HKCU; Subkey: "Software\NeuroShell"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\NeuroShell"; ValueType: string; ValueName: "Version";     ValueData: "{#MyAppVersion}"

; Run after install
[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

; Custom messages
[Messages]
WelcomeLabel2=This will install [name/ver] on your computer.%n%nNeuroShell is an AI-powered terminal that understands plain English.%n%nClick Next to continue.

[CustomMessages]
AppDescription=AI-Powered Terminal for Windows
