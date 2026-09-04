# File Search Service Uninstall Integration

This document describes how to properly uninstall the file search service when the application is uninstalled.

## Overview

The file search service (`HuGeScreenshot_FileSearch`) is a Windows service that provides fast file indexing using NTFS MFT. When the application is uninstalled, the service must be properly removed along with its index files.

## Files to Clean Up

| File | Location | Description |
|------|----------|-------------|
| `file_index.bin` | `%LOCALAPPDATA%\HuGeScreenshot\` | Main index file |
| `file_search_config.json` | `%LOCALAPPDATA%\HuGeScreenshot\` | Configuration file |
| Service executable | `<install_dir>\file-search-service.exe` | Service binary |

## NSIS Installer Integration

Add the following to your NSIS uninstaller script:

```nsis
Section "Uninstall"
  ; Stop and remove the file search service
  ; First, stop the service if running
  nsExec::ExecToLog 'sc stop "HuGeScreenshot_FileSearch"'
  
  ; Wait for service to stop (max 30 seconds)
  StrCpy $0 0
  ${DoWhile} $0 < 30
    nsExec::ExecToStack 'sc query "HuGeScreenshot_FileSearch"'
    Pop $1
    Pop $2
    ${If} $2 == ""
    ${OrIf} $1 != 0
      ${Break}
    ${EndIf}
    StrCmp $2 "STOPPED" done_waiting
    Sleep 1000
    IntOp $0 $0 + 1
  ${Loop}
  done_waiting:
  
  ; Delete the service
  nsExec::ExecToLog 'sc delete "HuGeScreenshot_FileSearch"'
  
  ; Wait for service deletion to complete
  Sleep 2000
  
  ; Clean up index files
  Delete "$LOCALAPPDATA\HuGeScreenshot\file_index.bin"
  Delete "$LOCALAPPDATA\HuGeScreenshot\file_search_config.json"
  
  ; Remove the HuGeScreenshot directory if empty
  RMDir "$LOCALAPPDATA\HuGeScreenshot"
  
  ; Remove service executable
  Delete "$INSTDIR\file-search-service.exe"
  
  ; ... rest of uninstall logic
SectionEnd
```

## WiX Installer Integration

Add the following to your WiX installer:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:util="http://wixtoolset.org/schemas/v4/wxs/util">
  
  <Fragment>
    <Component Id="FileSearchService" Directory="INSTALLFOLDER" Guid="YOUR-GUID-HERE">
      <!-- Service executable -->
      <File Id="FileSearchServiceExe" 
            Source="$(var.SourceDir)\file-search-service.exe" 
            KeyPath="yes" />
      
      <!-- Service installation -->
      <ServiceInstall Id="FileSearchServiceInstall"
                      Type="ownProcess"
                      Name="HuGeScreenshot_FileSearch"
                      DisplayName="虎哥截图文件搜索服务"
                      Description="提供快速文件搜索功能，通过读取 NTFS MFT 实现毫秒级全盘扫描"
                      Start="auto"
                      ErrorControl="normal"
                      Account="LocalSystem" />
      
      <!-- Service control - stop and remove on uninstall -->
      <ServiceControl Id="FileSearchServiceControl"
                      Name="HuGeScreenshot_FileSearch"
                      Stop="uninstall"
                      Remove="uninstall"
                      Wait="yes" />
    </Component>
    
    <!-- Clean up index files on uninstall -->
    <Component Id="CleanupIndexFiles" Directory="LocalAppDataFolder" Guid="YOUR-GUID-HERE">
      <RemoveFile Id="RemoveIndexFile" 
                  Name="file_index.bin" 
                  On="uninstall"
                  Directory="HuGeScreenshotDataDir" />
      <RemoveFile Id="RemoveConfigFile" 
                  Name="file_search_config.json" 
                  On="uninstall"
                  Directory="HuGeScreenshotDataDir" />
      <RemoveFolder Id="RemoveHuGeScreenshotDir" 
                    Directory="HuGeScreenshotDataDir" 
                    On="uninstall" />
    </Component>
    
    <!-- Directory definitions -->
    <Directory Id="LocalAppDataFolder">
      <Directory Id="HuGeScreenshotDataDir" Name="HuGeScreenshot" />
    </Directory>
  </Fragment>
</Wix>
```

## Tauri Bundler Integration

If using Tauri's built-in bundler with NSIS, add custom scripts in `tauri.conf.json`:

```json
{
  "bundle": {
    "windows": {
      "nsis": {
        "installerHooks": "./scripts/nsis-hooks.nsi"
      }
    }
  }
}
```

Create `scripts/nsis-hooks.nsi`:

```nsis
!macro customUnInstall
  ; Stop and remove file search service
  DetailPrint "Stopping file search service..."
  nsExec::ExecToLog 'sc stop "HuGeScreenshot_FileSearch"'
  Sleep 2000
  
  DetailPrint "Removing file search service..."
  nsExec::ExecToLog 'sc delete "HuGeScreenshot_FileSearch"'
  Sleep 2000
  
  ; Clean up index files
  DetailPrint "Cleaning up index files..."
  Delete "$LOCALAPPDATA\HuGeScreenshot\file_index.bin"
  Delete "$LOCALAPPDATA\HuGeScreenshot\file_search_config.json"
  RMDir "$LOCALAPPDATA\HuGeScreenshot"
!macroend
```

## Manual Uninstall via Command Line

Users can manually uninstall the service using these commands:

```powershell
# Stop the service
sc stop HuGeScreenshot_FileSearch

# Wait for it to stop
Start-Sleep -Seconds 2

# Delete the service
sc delete HuGeScreenshot_FileSearch

# Clean up index files
Remove-Item "$env:LOCALAPPDATA\HuGeScreenshot\file_index.bin" -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\HuGeScreenshot\file_search_config.json" -ErrorAction SilentlyContinue
```

Or use the service executable directly:

```powershell
# Run as Administrator
.\file-search-service.exe uninstall
```

## In-App Uninstall

The application provides a UI option in Settings > File Search > Service Management to uninstall the service manually. This calls the `uninstall_file_search_service` Tauri command which:

1. Stops the running service (if running)
2. Removes the service from Windows Service Control Manager
3. Optionally cleans up index files from disk

## API Reference

### Tauri Commands

#### `uninstall_file_search_service`

Uninstalls the file search service.

**Parameters:**
- `cleanup_index` (optional, boolean): Whether to also delete index files. Default: `true`

**Returns:**
```typescript
interface ServiceInstallResult {
  success: boolean;
  message: string;
  needsRestart: boolean;
}
```

#### `get_index_files_path`

Returns the path to the directory containing index files.

**Returns:** `string` - Path to the index files directory (e.g., `C:\Users\<user>\AppData\Local\HuGeScreenshot`)

## Troubleshooting

### Service marked for deletion

If you see "The specified service has been marked for deletion", this means the service is still in use. Wait a few seconds and try again, or restart the computer.

### Access denied

Service operations require administrator privileges. Ensure the uninstaller is running with elevated permissions.

### Index files locked

If index files cannot be deleted, ensure the service has fully stopped. The service saves the index on shutdown, which may take a few seconds.
