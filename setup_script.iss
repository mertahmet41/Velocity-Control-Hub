; Inno Setup Script for Velocity Control Hub
[Setup]
AppId={{9F47C9D2-113B-441A-9721-3DA6D12E08A9}
AppName=Velocity Control Hub
AppVersion=3.9.0
AppVerName=Velocity Control Hub 3.9.0
AppPublisher=Wumpus
AppPublisherURL=https://github.com/mertahmet41/Velocity-Control-Hub
AppSupportURL=https://github.com/mertahmet41/Velocity-Control-Hub
AppUpdatesURL=https://github.com/mertahmet41/Velocity-Control-Hub
DefaultDirName={autopf}\Velocity Control Hub
DefaultGroupName=Velocity Control Hub
AllowNoIcons=yes
OutputDir=C:\Users\amome\Desktop\VelocityControlHub\dist
OutputBaseFilename=Velocity_Control_Hub_Setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\VelocityControlHub.exe

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "C:\Users\amome\Desktop\VelocityControlHub\dist\VelocityControlHub.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\VelocityControlHub\OpenFFBoard_F411CE_V3_Profiles.hex"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\VelocityControlHub\index.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\VelocityControlHub\pro_wheel.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\VelocityControlHub\wheel.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Velocity Control Hub"; Filename: "{app}\VelocityControlHub.exe"
Name: "{group}\{cm:UninstallProgram,Velocity Control Hub}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Velocity Control Hub"; Filename: "{app}\VelocityControlHub.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VelocityControlHub.exe"; Description: "{cm:LaunchProgram,Velocity Control Hub}"; Flags: nowait postinstall skipifsilent
