; Script de Inno Setup 6 para Simulador de Flujo de Fluidos
; Compila la carpeta generada por PyInstaller (--onedir) en un instalador auto-actualizable.
; La versión proviene de un único lugar (VERSION_APP en ui/constantes.py) y se recibe por /DMyAppVersion=...

#ifndef MyAppVersion
  #error "Debes indicar la versión con /DMyAppVersion=X.Y.Z (leída desde ui.constantes.VERSION_APP)"
#endif

#define MyAppName "Simulador de Flujo de Fluidos"
#define MyAppPublisher "Luis Acevedo Suarez"
#define MyAppURL "https://github.com/luisacevedo15/Simulador-de-flujo-de-fluidos"
#define MyAppExeName "Simulador_Flujo_de_Fluidos.exe"
#define MyAppAssocExt ".sff"
#define MyAppAssocProgId "SimuladorFlujoFluidos.Proyecto"
#define MyAppAssocDesc "Proyecto de Simulador de Flujo de Fluidos"

[Setup]
AppId={{8F5E3B2A-6C4D-4E91-9A2B-7D4C3E1F8A01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=LICENSE
OutputDir=dist\installer
OutputBaseFilename=Simulador_Flujo_de_Fluidos_Setup
SetupIconFile=logo_1.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll,*.pyd
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\Simulador_Flujo_de_Fluidos\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "Gota_archivo_para_los_json.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocProgId}"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}"; ValueType: string; ValueName: "Content Type"; ValueData: "application/json"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocExt}"; ValueType: string; ValueName: "PerceivedType"; ValueData: "document"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocProgId}"; ValueType: string; ValueName: ""; ValueData: "{#MyAppAssocDesc}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocProgId}\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\Gota_archivo_para_los_json.ico,0"
Root: HKA; Subkey: "Software\Classes\{#MyAppAssocProgId}\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall
