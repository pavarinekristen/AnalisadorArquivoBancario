; Instalador Windows (Inno Setup 6). Antes: rodar instalador\gerar_pacote.bat.
; Instala em %LOCALAPPDATA% (sem precisar de administrador), cria atalho e preserva dados\ e config\ ao atualizar.

#define Nome "Conferência de Pagamentos"
#define Versao "2.0.0"

[Setup]
AppId={{6E7C2B1A-4F3D-4C9B-9A51-2C0E5D7F8A11}
AppName={#Nome}
AppVersion={#Versao}
AppPublisher=TechOne
DefaultDirName={localappdata}\ConferenciaPagamentos
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=saida
OutputBaseFilename=ConferenciaPagamentos-{#Versao}
SetupIconFile=..\assets\techone.ico
Compression=lzma2
SolidCompression=yes
LicenseFile=..\LICENSE

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "..\app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Conferir.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\conferencia\*"; DestDir: "{app}\conferencia"; Excludes: "__pycache__"; Flags: ignoreversion recursesubdirs
Source: "..\telas\*"; DestDir: "{app}\telas"; Excludes: "__pycache__"; Flags: ignoreversion recursesubdirs
Source: "..\regras\*"; DestDir: "{app}\regras"; Flags: ignoreversion onlyifdoesntexist
Source: "..\assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\.streamlit\config.toml"; DestDir: "{app}\.streamlit"; Flags: ignoreversion
Source: "..\config\cliente.exemplo.yaml"; DestDir: "{app}\config"; Flags: ignoreversion
Source: "pacote\python\*"; DestDir: "{app}\python"; Flags: ignoreversion recursesubdirs
Source: "pacote\wheels\*"; DestDir: "{app}\wheels"; Flags: ignoreversion
Source: "pacote\get-pip.py"; DestDir: "{app}\python"; Flags: ignoreversion

[Dirs]
Name: "{app}\dados"; Flags: uninsneveruninstall
Name: "{app}\config"; Flags: uninsneveruninstall

[Run]
Filename: "{app}\python\python.exe"; Parameters: """{app}\python\get-pip.py"" --no-index --find-links ""{app}\wheels"""; StatusMsg: "Preparando o Python..."; Flags: runhidden
Filename: "{app}\python\python.exe"; Parameters: "-m pip install --no-index --find-links ""{app}\wheels"" -r ""{app}\requirements.txt"""; StatusMsg: "Instalando dependências..."; Flags: runhidden
Filename: "{cmd}"; Parameters: "/c if not exist ""{app}\config\cliente.yaml"" copy ""{app}\config\cliente.exemplo.yaml"" ""{app}\config\cliente.yaml"""; Flags: runhidden

[Icons]
Name: "{userdesktop}\{#Nome}"; Filename: "{app}\python\python.exe"; Parameters: "-m streamlit run app.py --server.address 127.0.0.1 --server.headless false --browser.gatherUsageStats false"; WorkingDir: "{app}"; IconFilename: "{app}\assets\techone.ico"
