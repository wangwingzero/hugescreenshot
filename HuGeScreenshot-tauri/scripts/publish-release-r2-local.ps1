param(
    [string]$EnvFile,
    [string]$Version,
    [string]$ArtifactDir,
    [string]$ProductName,
    [string]$R2Bucket,
    [string]$R2Endpoint,
    [string]$ReleaseBaseUrl = "https://downloads.example.com",
    [string]$RcloneRemote = "r2:your-bucket",
    [string]$SshHost = "",
    [int]$SshPort = 22,
    [string]$SshUser = "root",
    [string]$SshKey = "",
    [string]$RemoteRoot = "",
    [switch]$UseAwsCli,
    [switch]$SkipBuild,
    [switch]$SkipNpmCi,
    [switch]$Clean,
    [switch]$SkipServerLatestMirror,
    [switch]$SkipServerArtifactMirror,
    [switch]$PurgeLatestCache
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Assert-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Missing command: $Name"
    }
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

function Invoke-Ssh {
    param([string]$Command)

    $arguments = @(
        "-i", $SshKey,
        "-p", [string]$SshPort,
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "$SshUser@$SshHost",
        $Command
    )
    Invoke-Checked -FilePath "ssh" -Arguments $arguments -WorkingDirectory $repoRoot
}

function Copy-ToServer {
    param(
        [string]$LocalPath,
        [string]$RemotePath
    )

    if (-not (Test-Path $LocalPath)) {
        throw "Local file not found: $LocalPath"
    }

    $arguments = @(
        "-i", $SshKey,
        "-P", [string]$SshPort,
        "-o", "IdentitiesOnly=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        $LocalPath,
        "$SshUser@$SshHost`:$RemotePath"
    )
    Invoke-Checked -FilePath "scp" -Arguments $arguments -WorkingDirectory $repoRoot
}

function Resolve-ConfigValue {
    param(
        [string]$PreferredValue,
        [string[]]$EnvNames,
        [string]$Label
    )

    if ($PreferredValue) {
        return $PreferredValue
    }

    foreach ($envName in $EnvNames) {
        $value = [System.Environment]::GetEnvironmentVariable($envName)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }

    throw "Missing $Label. Provide parameter or set one of: $($EnvNames -join ', ')"
}

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
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

        if (-not [System.Environment]::GetEnvironmentVariable($name)) {
            [System.Environment]::SetEnvironmentVariable($name, $value)
        }
    }
}

function Upload-FileToR2 {
    param(
        [string]$LocalPath,
        [string]$ObjectKey,
        [string]$ContentType,
        [string]$CacheControl,
        [string]$Bucket,
        [string]$Endpoint
    )

    $arguments = @(
        "s3", "cp",
        $LocalPath,
        "s3://$Bucket/$ObjectKey",
        "--endpoint-url", $Endpoint,
        "--content-type", $ContentType,
        "--cache-control", $CacheControl
    )
    Invoke-Checked -FilePath "aws" -Arguments $arguments -WorkingDirectory $repoRoot
}

function Upload-FileWithRclone {
    param(
        [string]$LocalPath,
        [string]$ObjectKey,
        [string]$ContentType,
        [string]$CacheControl,
        [string]$RemoteRoot
    )

    $remotePath = ($RemoteRoot.TrimEnd("/") + "/" + $ObjectKey.TrimStart("/"))
    $arguments = @(
        "copyto",
        $LocalPath,
        $remotePath,
        "--header-upload", "Content-Type: $ContentType",
        "--header-upload", "Cache-Control: $CacheControl"
    )
    Invoke-Checked -FilePath "rclone" -Arguments $arguments -WorkingDirectory $repoRoot
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$repoRoot = (Resolve-Path (Join-Path $projectRoot "..")).Path

if (-not $EnvFile) {
    $EnvFile = Join-Path $repoRoot ".env"
}
else {
    $EnvFile = (Resolve-Path $EnvFile).Path
}

if (-not (Test-Path $EnvFile)) {
    throw "Missing .env file: $EnvFile"
}

if (-not $ArtifactDir) {
    $ArtifactDir = Join-Path $repoRoot "build/local-release"
}
$artifactDirPath = [System.IO.Path]::GetFullPath($ArtifactDir)

Import-DotEnv -Path $EnvFile

$releaseBaseUrlEnv = [System.Environment]::GetEnvironmentVariable("R2_PUBLIC_URL")
if (-not $releaseBaseUrlEnv) {
    $releaseBaseUrlEnv = [System.Environment]::GetEnvironmentVariable("R2_DOMAIN")
}
if (-not $releaseBaseUrlEnv) {
    $releaseBaseUrlEnv = [System.Environment]::GetEnvironmentVariable("R2_PUBLIC_BASE_URL")
}
if ($releaseBaseUrlEnv -and -not $PSBoundParameters.ContainsKey("ReleaseBaseUrl")) {
    $ReleaseBaseUrl = $releaseBaseUrlEnv
}

$useRcloneUpload = (-not $UseAwsCli) -and $RcloneRemote -and (Get-Command "rclone" -ErrorAction SilentlyContinue)
$mirrorServerLatest = -not $SkipServerLatestMirror
$mirrorServerArtifacts = -not $SkipServerArtifactMirror
$needsServerAccess = $mirrorServerLatest -or $mirrorServerArtifacts

if (-not $useRcloneUpload) {
    $R2Bucket = Resolve-ConfigValue -PreferredValue $R2Bucket -EnvNames @("R2_BUCKET", "R2_BUCKET_NAME") -Label "R2 bucket"
    if (-not $R2Endpoint) {
        $accountId = [System.Environment]::GetEnvironmentVariable("R2_ACCOUNT_ID")
        if ($accountId) {
            $R2Endpoint = "https://$accountId.r2.cloudflarestorage.com"
        }
    }
    $R2Endpoint = Resolve-ConfigValue -PreferredValue $R2Endpoint -EnvNames @("R2_ENDPOINT") -Label "R2 endpoint"
}

try {
    Write-Step "Checking local publish prerequisites"
    if ($useRcloneUpload) {
        Assert-Command "rclone"
    }
    else {
        Assert-Command "aws"
    }
    Assert-Command "powershell"
    if ($needsServerAccess) {
        Assert-Command "ssh"
        Assert-Command "scp"
        if (-not (Test-Path $SshKey)) {
            throw "SSH key was not found: $SshKey"
        }
    }

    if (-not $useRcloneUpload) {
        if (-not [System.Environment]::GetEnvironmentVariable("AWS_ACCESS_KEY_ID")) {
            $accessKey = Resolve-ConfigValue -PreferredValue "" -EnvNames @("R2_ACCESS_KEY_ID") -Label "AWS_ACCESS_KEY_ID / R2_ACCESS_KEY_ID"
            [System.Environment]::SetEnvironmentVariable("AWS_ACCESS_KEY_ID", $accessKey)
        }
        if (-not [System.Environment]::GetEnvironmentVariable("AWS_SECRET_ACCESS_KEY")) {
            $secretKey = Resolve-ConfigValue -PreferredValue "" -EnvNames @("R2_SECRET_ACCESS_KEY") -Label "AWS_SECRET_ACCESS_KEY / R2_SECRET_ACCESS_KEY"
            [System.Environment]::SetEnvironmentVariable("AWS_SECRET_ACCESS_KEY", $secretKey)
        }
        if (-not [System.Environment]::GetEnvironmentVariable("AWS_DEFAULT_REGION")) {
            [System.Environment]::SetEnvironmentVariable("AWS_DEFAULT_REGION", "auto")
        }
    }

    if (-not $SkipBuild) {
        Write-Step "Building local release artifacts"
        $buildArgs = @(
            "-ExecutionPolicy", "Bypass",
            "-File", (Join-Path $scriptDir "build-release-local.ps1"),
            "-EnvFile", $EnvFile,
            "-ArtifactDir", $artifactDirPath,
            "-ReleaseBaseUrl", $ReleaseBaseUrl
        )
        if ($ProductName) {
            $buildArgs += @("-ProductName", $ProductName)
        }
        if ($Version) {
            $buildArgs += @("-Version", $Version)
        }
        if ($SkipNpmCi) {
            $buildArgs += "-SkipNpmCi"
        }
        if ($Clean) {
            $buildArgs += "-Clean"
        }
        Invoke-Checked -FilePath "powershell" -Arguments $buildArgs -WorkingDirectory $projectRoot
    }

    $manifestPath = Join-Path $artifactDirPath "manifest.local-release.json"
    $latestJsonPath = Join-Path $artifactDirPath "latest.local.json"

    if (-not (Test-Path $manifestPath)) {
        throw "Missing build manifest: $manifestPath"
    }
    if (-not (Test-Path $latestJsonPath)) {
        throw "Missing latest.local.json: $latestJsonPath"
    }

    $manifest = Get-Content $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $releaseVersion = [string]$manifest.version
    if ([string]::IsNullOrWhiteSpace($releaseVersion)) {
        throw "manifest.local-release.json does not contain version"
    }

    $remoteRootClean = $RemoteRoot.TrimEnd("/")

    Write-Step "Uploading versioned artifacts to R2"
    foreach ($artifact in $manifest.artifacts) {
        $artifactPath = [string]$artifact.path
        if (-not (Test-Path $artifactPath)) {
            throw "Artifact listed in manifest was not found: $artifactPath"
        }

        $name = [System.IO.Path]::GetFileName($artifactPath)
        $objectKey = "$releaseVersion/$name"
        $contentType = switch -Wildcard ($name) {
            "*.sig" { "text/plain; charset=utf-8"; break }
            "*.zip" { "application/zip"; break }
            "*.exe" { "application/octet-stream"; break }
            default { "application/octet-stream" }
        }
        if ($useRcloneUpload) {
            Upload-FileWithRclone `
                -LocalPath $artifactPath `
                -ObjectKey $objectKey `
                -ContentType $contentType `
                -CacheControl "public, max-age=31536000, immutable" `
                -RemoteRoot $RcloneRemote
        }
        else {
            Upload-FileToR2 `
                -LocalPath $artifactPath `
                -ObjectKey $objectKey `
                -ContentType $contentType `
                -CacheControl "public, max-age=31536000, immutable" `
                -Bucket $R2Bucket `
                -Endpoint $R2Endpoint
        }
    }

    if ($mirrorServerArtifacts) {
        $remoteVersionDir = "$remoteRootClean/$releaseVersion"
        $remoteTmpDir = "$remoteRootClean/.upload-$releaseVersion-$(Get-Date -Format yyyyMMddHHmmss)"

        Write-Step "Mirroring versioned artifacts to VPS download path"
        Invoke-Ssh "mkdir -p '$remoteTmpDir' '$remoteVersionDir'"

        foreach ($artifact in $manifest.artifacts) {
            $artifactPath = [string]$artifact.path
            if (-not (Test-Path $artifactPath)) {
                throw "Artifact listed in manifest was not found: $artifactPath"
            }

            $name = [System.IO.Path]::GetFileName($artifactPath)
            Copy-ToServer -LocalPath $artifactPath -RemotePath "$remoteTmpDir/$name"
        }

        Invoke-Ssh "cp -f '$remoteTmpDir'/* '$remoteVersionDir'/ && rm -rf '$remoteTmpDir' && chmod -R a+r '$remoteVersionDir'"
    }

    Write-Step "Publishing latest.json"
    if ($useRcloneUpload) {
        Upload-FileWithRclone `
            -LocalPath $latestJsonPath `
            -ObjectKey "latest.json" `
            -ContentType "application/json; charset=utf-8" `
            -CacheControl "no-store, no-cache, must-revalidate, max-age=0" `
            -RemoteRoot $RcloneRemote
    }
    else {
        Upload-FileToR2 `
            -LocalPath $latestJsonPath `
            -ObjectKey "latest.json" `
            -ContentType "application/json; charset=utf-8" `
            -CacheControl "no-store, no-cache, must-revalidate, max-age=0" `
            -Bucket $R2Bucket `
            -Endpoint $R2Endpoint
    }

    if ($mirrorServerLatest) {
        Write-Step "Mirroring latest.json to VPS updater endpoint"
        Copy-ToServer -LocalPath $latestJsonPath -RemotePath "$remoteRootClean/latest.json.tmp"
        Invoke-Ssh "mv -f '$remoteRootClean/latest.json.tmp' '$remoteRootClean/latest.json' && chmod a+r '$remoteRootClean/latest.json'"
    }

    if ($PurgeLatestCache) {
        $zoneId = [System.Environment]::GetEnvironmentVariable("CF_ZONE_ID")
        $apiToken = [System.Environment]::GetEnvironmentVariable("CF_API_TOKEN")
        $apiKey = [System.Environment]::GetEnvironmentVariable("CF_API_KEY")
        $authEmail = [System.Environment]::GetEnvironmentVariable("CF_AUTH_EMAIL")
        if ($zoneId -and ($apiToken -or ($apiKey -and $authEmail))) {
            Write-Step "Purging Cloudflare cache for latest.json"
            $latestUrl = ($ReleaseBaseUrl.TrimEnd("/") + "/latest.json")
            $body = @{ files = @($latestUrl) } | ConvertTo-Json -Depth 3
            if ($apiToken) {
                Invoke-RestMethod `
                    -Method Post `
                    -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/purge_cache" `
                    -Headers @{ Authorization = "Bearer $apiToken" } `
                    -ContentType "application/json" `
                    -Body $body | Out-Null
            }
            else {
                Invoke-RestMethod `
                    -Method Post `
                    -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/purge_cache" `
                    -Headers @{ "X-Auth-Email" = $authEmail; "X-Auth-Key" = $apiKey } `
                    -ContentType "application/json" `
                    -Body $body | Out-Null
            }
        }
        else {
            Write-Warning "CF_ZONE_ID with CF_API_TOKEN or CF_API_KEY/CF_AUTH_EMAIL not configured; skipped cache purge."
        }
    }

    Write-Step "R2 publish completed"
    Write-Host "Version      : $releaseVersion" -ForegroundColor Green
    if ($useRcloneUpload) {
        Write-Host "Uploader     : rclone"
        Write-Host "Remote       : $RcloneRemote"
    }
    else {
        Write-Host "Uploader     : aws"
        Write-Host "Bucket       : $R2Bucket"
        Write-Host "Endpoint     : $R2Endpoint"
    }
    Write-Host "Latest JSON  : $($ReleaseBaseUrl.TrimEnd('/'))/latest.json"
    if ($mirrorServerArtifacts) {
        Write-Host "VPS download : $($ReleaseBaseUrl.TrimEnd('/'))/$releaseVersion/"
    }
    if ($mirrorServerLatest) {
        Write-Host "VPS manifest : $($ReleaseBaseUrl.TrimEnd('/'))/latest.json"
    }
}
finally {
    # no-op
}
