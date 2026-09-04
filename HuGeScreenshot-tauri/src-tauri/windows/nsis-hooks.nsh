!macro NSIS_HOOK_POSTINSTALL
  DetailPrint "Installing Microsoft Visual C++ Redistributable x64 for local OCR..."

  ${If} ${FileExists} "$INSTDIR\resources\vc_redist.x64.exe"
    ExecWait '"$INSTDIR\resources\vc_redist.x64.exe" /install /quiet /norestart' $0

    ${If} $0 == 0
      DetailPrint "Microsoft Visual C++ Redistributable x64 is installed."
    ${ElseIf} $0 == 3010
      DetailPrint "Microsoft Visual C++ Redistributable x64 installed; restart may be required."
    ${ElseIf} $0 == 1638
      DetailPrint "Microsoft Visual C++ Redistributable x64 is already installed."
    ${Else}
      MessageBox MB_ICONEXCLAMATION|MB_OK "Microsoft Visual C++ 运行库安装失败（错误码：$0）。本地 OCR 可能无法启动；请重新运行安装器，或手动安装 Microsoft Visual C++ 2015-2022 Redistributable x64。"
    ${EndIf}
  ${Else}
    MessageBox MB_ICONEXCLAMATION|MB_OK "安装包缺少 Microsoft Visual C++ 运行库。本地 OCR 可能无法启动；请重新下载安装包后重试。"
  ${EndIf}
!macroend
