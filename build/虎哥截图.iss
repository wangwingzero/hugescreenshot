; =====================================================
; 虎哥截图 - Inno Setup 安装脚本
; =====================================================
;
; 使用方法：
;   1. 先用 PyInstaller 打包: pyinstaller build/虎哥截图-dir.spec --noconfirm --clean
;   2. 生成清单: python build/generate_manifest.py
;   3. 编译安装包: iscc build/虎哥截图.iss
;
; 输出：
;   dist/HuGeScreenshot-{版本号}-Setup.exe
;
; 静默安装支持：
;   /SILENT - 静默安装（显示进度条）
;   /VERYSILENT - 完全静默安装（无界面）
;   /DIR="path" - 指定安装目录
;   /CLOSEAPPLICATIONS - 自动关闭正在运行的应用
;
; Feature: fullupdate-inplace-install
; Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 4.1, 4.2, 4.3, 4.4

#define MyAppName "虎哥截图"
#define MyAppVersion "2.11.0"
#define MyAppPublisher "虎哥截图"
#define MyAppURL "https://github.com/wangwingzero/hugescreenshot"
#define MyAppExeName "虎哥截图.exe"

[Setup]
; 应用信息
AppId={{A8E5F3D2-9B4C-4E7A-8F1D-6C3B2A1E0D9F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安装目录
DefaultDirName=D:\虎哥截图
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; 输出设置
OutputDir=..\dist
OutputBaseFilename=HuGeScreenshot-{#MyAppVersion}-Setup
SetupIconFile=..\resources\虎哥截图.ico

; 压缩设置
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4

; 权限设置（不需要管理员权限）
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; 安装向导设置
WizardStyle=modern
WizardSizePercent=100
DisableWelcomePage=no
DisableDirPage=no
DisableReadyPage=no
ShowLanguageDialog=auto

; 版本信息
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoCopyright=Copyright (C) 2024-2026 {#MyAppPublisher}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

; 卸载设置
UninstallDisplayName={#MyAppName}
CreateUninstallRegKey=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Messages]
chinesesimplified.BeveledLabel=简体中文

[Files]
; 主程序和所有依赖文件
Source: "..\dist\虎哥截图\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 桌面快捷方式（始终创建）
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

; 开始菜单快捷方式（始终创建）
Name: "{userprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userprograms}\{#MyAppName}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
; 安装完成后启动程序
; 注意：使用 postinstall 而不是 skipifsilent，这样静默安装也会启动程序
; Feature: fullupdate-inplace-install
; Requirements: 4.4
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall

[UninstallDelete]
; 卸载时删除的额外文件（不删除用户数据）
Type: files; Name: "{app}\manifest.json"
Type: files; Name: "{app}\*.log"
Type: dirifempty; Name: "{app}"

[Code]
// ========== Pascal 脚本 ==========

var
  IsUpgrade: Boolean;

// 检查应用是否正在运行
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  // 使用 tasklist 检查进程
  Result := False;
  if Exec('cmd.exe', '/c tasklist /FI "IMAGENAME eq 虎哥截图.exe" 2>NUL | find /I "虎哥截图.exe" >NUL', 
          '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    Result := (ResultCode = 0);
  end;
end;

// 尝试关闭正在运行的应用
function CloseRunningApp(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec('cmd.exe', '/c taskkill /F /IM "虎哥截图.exe" 2>NUL', 
                 '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  // 等待进程完全退出
  Sleep(1000);
end;

// 安装前初始化
// Feature: fullupdate-inplace-install
// Requirements: 4.3
function InitializeSetup(): Boolean;
var
  RetryCount: Integer;
  IsSilent: Boolean;
begin
  Result := True;
  RetryCount := 0;
  IsSilent := WizardSilent();
  
  // 检查是否正在运行
  while IsAppRunning() and (RetryCount < 3) do
  begin
    if IsSilent then
    begin
      // 静默模式下自动关闭应用
      CloseRunningApp();
      Sleep(500);
    end
    else if MsgBox('虎哥截图正在运行。' + #13#10 + #13#10 + 
              '点击"是"自动关闭程序并继续安装，' + #13#10 +
              '点击"否"手动关闭后重试。',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      CloseRunningApp();
      Sleep(500);
    end
    else
    begin
      if MsgBox('请手动关闭虎哥截图后点击"重试"，' + #13#10 +
                '或点击"取消"退出安装。',
                mbError, MB_RETRYCANCEL) = IDCANCEL then
      begin
        Result := False;
        Exit;
      end;
    end;
    RetryCount := RetryCount + 1;
  end;
  
  // 最终检查
  if IsAppRunning() then
  begin
    if not IsSilent then
    begin
      MsgBox('无法关闭虎哥截图，请手动关闭后重新运行安装程序。', mbError, MB_OK);
    end;
    Result := False;
  end;
end;

// 安装向导初始化
procedure InitializeWizard();
begin
  // 在 InitializeWizard 中不能使用 {app}，因为用户还没选择安装目录
  // 升级检测移到 CurStepChanged
end;

// 安装步骤变化时检查
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    // 此时 {app} 已经确定，可以检查是否为升级安装
    IsUpgrade := FileExists(ExpandConstant('{app}\{#MyAppExeName}'));
  end;
end;

// 卸载前初始化
function InitializeUninstall(): Boolean;
var
  RetryCount: Integer;
begin
  Result := True;
  RetryCount := 0;
  
  // 检查是否正在运行
  while IsAppRunning() and (RetryCount < 3) do
  begin
    if MsgBox('虎哥截图正在运行，需要先关闭才能卸载。' + #13#10 + #13#10 + 
              '点击"是"自动关闭程序，' + #13#10 +
              '点击"否"手动关闭后重试。',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      CloseRunningApp();
      Sleep(500);
    end
    else
    begin
      if MsgBox('请手动关闭虎哥截图后点击"重试"，' + #13#10 +
                '或点击"取消"退出卸载。',
                mbError, MB_RETRYCANCEL) = IDCANCEL then
      begin
        Result := False;
        Exit;
      end;
    end;
    RetryCount := RetryCount + 1;
  end;
  
  // 最终检查
  if IsAppRunning() then
  begin
    MsgBox('无法关闭虎哥截图，请手动关闭后重新运行卸载程序。', mbError, MB_OK);
    Result := False;
  end;
end;

// 卸载完成后提示
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // 提示用户数据保留
    if MsgBox('虎哥截图已卸载完成。' + #13#10 + #13#10 +
              '用户配置和日志文件保存在：' + #13#10 +
              ExpandConstant('{userappdata}') + '\.screenshot_tool\' + #13#10 + #13#10 +
              '是否删除这些用户数据？',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\.screenshot_tool'), True, True, True);
    end;
  end;
end;
