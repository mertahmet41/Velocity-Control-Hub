; Inno Setup Script for Velocity Control Hub
[Setup]
AppId={{9F47C9D2-113B-441A-9721-3DA6D12E08A9}
AppName=Velocity Control Hub
AppVersion=3.18.0
AppVerName=Velocity Control Hub 3.18.0
AppPublisher=Wumpus
AppPublisherURL=https://github.com/mertahmet41/Velocity-Control-Hub
AppSupportURL=https://github.com/mertahmet41/Velocity-Control-Hub
AppUpdatesURL=https://github.com/mertahmet41/Velocity-Control-Hub
DefaultDirName={autopf}\Velocity Control Hub
DefaultGroupName=Velocity Control Hub
AllowNoIcons=yes
OutputDir=C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\dist
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
Source: "C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\dist\VelocityControlHub.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\Firmware\OpenFFBoard_F411CE_V3_Profiles_v3.18.0.hex"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\Firmware\OpenFFBoard_F411CE_V3_Profiles_v3.18.0.hex"; DestDir: "{app}\Firmware"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\version.json"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\index.html"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\pro_wheel.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "C:\Users\amome\Desktop\Direksiyon_Projesi\Velocity-Control-Hub\wheel.png"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Velocity Control Hub"; Filename: "{app}\VelocityControlHub.exe"
Name: "{group}\{cm:UninstallProgram,Velocity Control Hub}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Velocity Control Hub"; Filename: "{app}\VelocityControlHub.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\VelocityControlHub.exe"; Description: "{cm:LaunchProgram,Velocity Control Hub}"; Flags: nowait postinstall skipifsilent

