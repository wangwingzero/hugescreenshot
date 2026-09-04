param(
    [string]$EnvFile,
    [string]$Version,
    [string]$ProductName,
    [string]$ArtifactDir,
    [string]$ReleaseBaseUrl = "https://downloads.example.com",
    [switch]$SkipNpmCi,
    [switch]$SkipFrontendBuild,
    [switch]$SkipLatestJson,
    [switch]$Clean,
    [switch]$CiMode
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )

    Write-Host "[$WorkingDirectory] $FilePath $($Arguments -join ' ')"
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed: $FilePath $($Arguments -join ' ')"
        }
    }
    finally {
        Pop-Location
    }
}

function Get-CommandVersion {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    $output = & $FilePath @Arguments 2>$null
    if ($LASTEXITCODE -ne 0) {
        return "unknown"
    }

    return (($output | Select-Object -First 1) -join "").Trim()
}

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing command: $Name"
    }
}

function Test-NodeModuleResolvable {
    param(
        [string]$ModuleName,
        [string]$WorkingDirectory
    )

    $modulePath = Join-Path $WorkingDirectory ("node_modules\" + ($ModuleName -replace "/", "\"))
    return (Test-Path $modulePath)
}

function Use-TemporaryFile {
    param(
        [string]$Source,
        [string]$Destination
    )

    $backup = $null
    $targetDir = Split-Path -Parent $Destination
    if ($targetDir) {
        New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    }

    if (Test-Path $Destination) {
        $backup = Join-Path ([System.IO.Path]::GetTempPath()) ("hugescreenshot-backup-" + [System.Guid]::NewGuid().ToString("N"))
        Copy-Item $Destination $backup -Force
    }

    $sourcePath = [System.IO.Path]::GetFullPath($Source)
    $destinationPath = [System.IO.Path]::GetFullPath($Destination)
    if ($sourcePath -ne $destinationPath) {
        Copy-Item $Source $Destination -Force
    }

    return $backup
}

function Restore-TemporaryFile {
    param(
        [string]$Destination,
        [string]$Backup
    )

    if ($Backup) {
        Copy-Item $Backup $Destination -Force
        Remove-Item $Backup -Force
        return
    }

    if (Test-Path $Destination) {
        Remove-Item $Destination -Force
    }
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        throw "Missing .env file: $Path"
    }

    Get-Content $Path -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            return
        }

        $match = [regex]::Match($line, "^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$")
        if (-not $match.Success) {
            return
        }

        $name = $match.Groups[1].Value
        $value = $match.Groups[2].Value.Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path "Env:$name" -Value $value
    }
}

function Set-Utf8NoBomContent {
    param(
        [string]$Path,
        [string]$Value
    )

    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Value, $encoding)
}

function Test-SameFileContent {
    param(
        [string]$Left,
        [string]$Right
    )

    if (-not (Test-Path $Left) -or -not (Test-Path $Right)) {
        return $false
    }

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $leftStream = [System.IO.File]::OpenRead($Left)
        try {
            $leftHash = [System.BitConverter]::ToString($sha256.ComputeHash($leftStream))
        }
        finally {
            $leftStream.Dispose()
        }

        $rightStream = [System.IO.File]::OpenRead($Right)
        try {
            $rightHash = [System.BitConverter]::ToString($sha256.ComputeHash($rightStream))
        }
        finally {
            $rightStream.Dispose()
        }

        return $leftHash -eq $rightHash
    }
    finally {
        $sha256.Dispose()
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$repoRoot = (Resolve-Path (Join-Path $projectRoot "..")).Path
$srcTauriDir = Join-Path $projectRoot "src-tauri"
$cargoTargetRoot = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { Join-Path $srcTauriDir "target" }
$bundleDir = Join-Path $cargoTargetRoot "release/bundle/nsis"

if (-not $EnvFile) {
    $EnvFile = Join-Path $repoRoot ".env"
}
else {
    $EnvFile = (Resolve-Path $EnvFile).Path
}

if (-not (Test-Path $EnvFile)) {
    throw "Missing .env file for build: $EnvFile"
}

if (-not $ArtifactDir) {
    $ArtifactDir = Join-Path $repoRoot "build/local-release"
}

$artifactDirPath = [System.IO.Path]::GetFullPath($ArtifactDir)
$rootEnvPath = Join-Path $repoRoot ".env"
$srcTauriEnvPath = Join-Path $srcTauriDir ".env"
$rootEnvBackup = $null
$srcTauriEnvBackup = $null
$rootEnvManaged = $false
$srcTauriEnvManaged = $false
$tempConfigPath = $null
$proxyEnvNames = @("ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY")
$proxyEnvBackup = @{}
foreach ($name in $proxyEnvNames) {
    $proxyEnvBackup[$name] = [System.Environment]::GetEnvironmentVariable($name)
}

try {
    Write-Step "Checking local toolchain"
    Assert-Command "node"
    Assert-Command "npm"
    Assert-Command "rustc"
    Assert-Command "cargo"

    $nodeVersion = Get-CommandVersion "node" @("--version")
    $npmVersion = Get-CommandVersion "npm" @("--version")
    $rustVersion = Get-CommandVersion "rustc" @("--version")

    Write-Host "Node   : $nodeVersion"
    Write-Host "npm    : $npmVersion"
    Write-Host "Rust   : $rustVersion"

    if ($Clean) {
        Write-Step "Cleaning previous build outputs"
        $pathsToClean = @(
            (Join-Path $projectRoot "dist"),
            (Join-Path $srcTauriDir "target/release/bundle"),
            $artifactDirPath
        )
        foreach ($path in $pathsToClean) {
            if (Test-Path $path) {
                Remove-Item $path -Recurse -Force
            }
        }
    }

    Write-Step "Preparing .env for CI-parity build"
    if ([System.IO.Path]::GetFullPath($EnvFile) -ne [System.IO.Path]::GetFullPath($rootEnvPath)) {
        $rootEnvBackup = Use-TemporaryFile -Source $EnvFile -Destination $rootEnvPath
        $rootEnvManaged = $true
    }
    if (-not (Test-SameFileContent -Left $rootEnvPath -Right $srcTauriEnvPath)) {
        $srcTauriEnvBackup = Use-TemporaryFile -Source $rootEnvPath -Destination $srcTauriEnvPath
        $srcTauriEnvManaged = $true
    }
    Write-Host "Using env file: $rootEnvPath"
    Import-DotEnv -Path $rootEnvPath

    if (-not $SkipNpmCi) {
        Write-Step "Installing frontend dependencies with npm ci"
        Invoke-Checked -FilePath "npm" -Arguments @("ci") -WorkingDirectory $projectRoot
    }

    if (($env:OS -eq "Windows_NT") -and -not (Test-NodeModuleResolvable -ModuleName "@tauri-apps/cli-win32-x64-msvc" -WorkingDirectory $projectRoot)) {
        Write-Step "Repairing missing Tauri Windows native binding"
        Invoke-Checked -FilePath "npm" -Arguments @("install", "@tauri-apps/cli-win32-x64-msvc@2.9.6", "--no-save", "--os=win32", "--cpu=x64") -WorkingDirectory $projectRoot
    }

    $packageJson = Get-Content (Join-Path $projectRoot "package.json") -Raw | ConvertFrom-Json
    $tauriConfig = Get-Content (Join-Path $srcTauriDir "tauri.conf.json") -Raw -Encoding UTF8 | ConvertFrom-Json
    $effectiveProductName = if ($ProductName) { $ProductName } else { $tauriConfig.productName }
    if (-not $Version) {
        $Version = "v$($packageJson.version)"
    }
    elseif (-not $Version.StartsWith("v")) {
        $Version = "v$Version"
    }
    $versionNumber = $Version.TrimStart("v")

    Write-Step "Clearing stale NSIS artifacts (best effort)"
    if (Test-Path $bundleDir) {
        try {
            Remove-Item $bundleDir -Recurse -Force
        }
        catch {
            Write-Warning "Could not clear stale NSIS artifacts; will collect only $Version artifacts. $($_.Exception.Message)"
        }
    }

    Write-Step "Running Tauri release build"
    if ($env:TAURI_PRIVATE_KEY -and -not $env:TAURI_SIGNING_PRIVATE_KEY) {
        $env:TAURI_SIGNING_PRIVATE_KEY = $env:TAURI_PRIVATE_KEY
    }
    if ($env:TAURI_PRIVATE_KEY_PASSWORD -and -not $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD) {
        $env:TAURI_SIGNING_PRIVATE_KEY_PASSWORD = $env:TAURI_PRIVATE_KEY_PASSWORD
    }
    if (-not $env:TAURI_SIGNING_PRIVATE_KEY) {
        Write-Warning "TAURI_SIGNING_PRIVATE_KEY/TAURI_PRIVATE_KEY is missing; updater signature artifacts may be skipped."
    }
    $tauriCli = Join-Path $projectRoot "node_modules\.bin\tauri.cmd"
    if (-not (Test-Path $tauriCli)) {
        throw "Tauri CLI launcher not found: $tauriCli"
    }
    $tauriBuildArgs = @("build")
    $tauriConfigOverride = @{}
    if ($ProductName) {
        $tauriConfigOverride.productName = $ProductName
    }
    if ($SkipFrontendBuild) {
        $tauriConfigOverride.build = @{
            beforeBuildCommand = ""
        }
    }
    if ($tauriConfigOverride.Count -gt 0) {
        $tauriConfigJson = $tauriConfigOverride | ConvertTo-Json -Compress -Depth 5
        $tempConfigPath = Join-Path ([System.IO.Path]::GetTempPath()) ("hugescreenshot-tauri-config-" + [System.Guid]::NewGuid().ToString("N") + ".json")
        Set-Utf8NoBomContent -Path $tempConfigPath -Value $tauriConfigJson
        $tauriBuildArgs += @("--config", $tempConfigPath)
    }
    Invoke-Checked -FilePath $tauriCli -Arguments $tauriBuildArgs -WorkingDirectory $projectRoot

    if (-not (Test-Path $bundleDir)) {
        throw "NSIS output directory not found: $bundleDir"
    }

    Write-Step "Collecting build artifacts"
    New-Item -ItemType Directory -Path $artifactDirPath -Force | Out-Null
    $artifactPatterns = @("*.exe", "*.exe.sig", "*.nsis.zip", "*.nsis.zip.sig")
    $artifacts = @()
    foreach ($pattern in $artifactPatterns) {
        $artifacts += Get-ChildItem -Path $bundleDir -Filter $pattern -File -ErrorAction SilentlyContinue
    }
    $artifacts = @($artifacts | Where-Object { $_ -ne $null -and $_.Name -like "*_$versionNumber`_*" } | Sort-Object FullName -Unique)
    if ($artifacts.Count -eq 0) {
        throw "No NSIS artifacts were found for $Version."
    }

    $localArtifacts = @()
    foreach ($artifact in $artifacts) {
        $localArtifactPath = Join-Path $artifactDirPath $artifact.Name
        Copy-Item $artifact.FullName $localArtifactPath -Force
        $localArtifacts += Get-Item $localArtifactPath
    }

    $manifest = [ordered]@{
        version = $Version
        productName = $effectiveProductName
        generatedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        envFile = $EnvFile
        ciMode = [bool]$CiMode
        artifacts = @($localArtifacts | ForEach-Object {
            [ordered]@{
                name = $_.Name
                size = $_.Length
                path = $_.FullName
            }
        })
    }

    $manifestPath = Join-Path $artifactDirPath "manifest.local-release.json"
    Set-Utf8NoBomContent -Path $manifestPath -Value ($manifest | ConvertTo-Json -Depth 5)

    if (-not $SkipLatestJson) {
        $exeFile = $localArtifacts | Where-Object { $_.Extension -eq ".exe" -and $_.Name -notlike "*.nsis.zip*" } | Select-Object -First 1
        $sigFile = $localArtifacts | Where-Object { $_.Name -like "*.exe.sig" -and $_.Name -notlike "*.nsis.zip*" } | Select-Object -First 1
        if ($exeFile -and $sigFile) {
            $sig = (Get-Content $sigFile.FullName -Raw).Trim()
            $encodedExeName = [System.Uri]::EscapeDataString($exeFile.Name)
            $latestJson = [ordered]@{
                version = $Version
                notes = "HuGeScreenshot $Version local CI parity build"
                pub_date = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
                platforms = @{
                    "windows-x86_64" = @{
                        signature = $sig
                        url = "$ReleaseBaseUrl/$Version/$encodedExeName"
                    }
                }
            }
            $latestJsonPath = Join-Path $artifactDirPath "latest.local.json"
            Set-Utf8NoBomContent -Path $latestJsonPath -Value ($latestJson | ConvertTo-Json -Depth 5)
        }
        else {
            Write-Warning "Missing .exe or .exe.sig; skipped latest.local.json generation."
        }
    }

    Write-Step "Build completed"
    Write-Host "Artifact directory: $artifactDirPath" -ForegroundColor Green
    Get-ChildItem $artifactDirPath -File | Sort-Object Name | ForEach-Object {
        Write-Host ("{0,12} {1}" -f $_.Length, $_.FullName)
    }
}
finally {
    if ($tempConfigPath -and (Test-Path $tempConfigPath)) {
        Remove-Item $tempConfigPath -Force -ErrorAction SilentlyContinue
    }
    foreach ($name in $proxyEnvBackup.Keys) {
        $value = $proxyEnvBackup[$name]
        if ($null -eq $value -or $value -eq "") {
            Remove-Item "Env:$name" -ErrorAction SilentlyContinue
        }
        else {
            Set-Item "Env:$name" $value
        }
    }
    if ($srcTauriEnvManaged) {
        Restore-TemporaryFile -Destination $srcTauriEnvPath -Backup $srcTauriEnvBackup
    }
    if ($rootEnvManaged) {
        Restore-TemporaryFile -Destination $rootEnvPath -Backup $rootEnvBackup
    }
}
