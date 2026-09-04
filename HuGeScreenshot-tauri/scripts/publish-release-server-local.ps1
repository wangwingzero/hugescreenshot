param(
    [string]$EnvFile,
    [string]$Version,
    [string]$ArtifactDir,
    [string]$ProductName,
    [string]$ReleaseBaseUrl = "https://downloads.example.com",
    [string]$CfUpdateBaseUrl = "https://downloads.example.com",
    [string]$SshHost = "",
    [int]$SshPort = 22,
    [string]$SshUser = "root",
    [string]$SshKey = "",
    [string]$RemoteRoot = "",
    [switch]$SkipBuild,
    [switch]$SkipNpmCi,
    [switch]$Clean,
    [switch]$SkipPurge,
    [switch]$SkipPrefetch
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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDir "..")).Path
$repoRoot = (Resolve-Path (Join-Path $projectRoot "..")).Path

if (-not $EnvFile) {
    $EnvFile = Join-Path $repoRoot ".env"
}
elseif (Test-Path $EnvFile) {
    $EnvFile = (Resolve-Path $EnvFile).Path
}

if (-not $ArtifactDir) {
    $ArtifactDir = Join-Path $repoRoot "build/local-release"
}
$artifactDirPath = [System.IO.Path]::GetFullPath($ArtifactDir)
Import-DotEnv -Path $EnvFile

if (-not $PSBoundParameters.ContainsKey("ReleaseBaseUrl")) {
    $envReleaseBaseUrl = [System.Environment]::GetEnvironmentVariable("HUGESCREENSHOT_RELEASE_BASE_URL")
    if (-not $envReleaseBaseUrl) {
        $envReleaseBaseUrl = [System.Environment]::GetEnvironmentVariable("RELEASE_BASE_URL")
    }
    if ($envReleaseBaseUrl) {
        $ReleaseBaseUrl = $envReleaseBaseUrl
    }
}
if (-not $PSBoundParameters.ContainsKey("CfUpdateBaseUrl")) {
    $envCfUpdateBaseUrl = [System.Environment]::GetEnvironmentVariable("HUGESCREENSHOT_CF_UPDATE_BASE_URL")
    if ($envCfUpdateBaseUrl) {
        $CfUpdateBaseUrl = $envCfUpdateBaseUrl
    }
}
if (-not $PSBoundParameters.ContainsKey("SshHost")) {
    $envSshHost = [System.Environment]::GetEnvironmentVariable("RELEASE_SSH_HOST")
    if ($envSshHost) {
        $SshHost = $envSshHost
    }
}
if (-not $PSBoundParameters.ContainsKey("SshPort")) {
    $envSshPort = [System.Environment]::GetEnvironmentVariable("RELEASE_SSH_PORT")
    if ($envSshPort) {
        $SshPort = [int]$envSshPort
    }
}
if (-not $PSBoundParameters.ContainsKey("SshUser")) {
    $envSshUser = [System.Environment]::GetEnvironmentVariable("RELEASE_SSH_USER")
    if ($envSshUser) {
        $SshUser = $envSshUser
    }
}
if (-not $PSBoundParameters.ContainsKey("SshKey")) {
    $envSshKey = [System.Environment]::GetEnvironmentVariable("RELEASE_SSH_KEY")
    if ($envSshKey) {
        $SshKey = $envSshKey
    }
}
if (-not $PSBoundParameters.ContainsKey("RemoteRoot")) {
    $envRemoteRoot = [System.Environment]::GetEnvironmentVariable("RELEASE_REMOTE_DIR")
    if ($envRemoteRoot) {
        $RemoteRoot = $envRemoteRoot
    }
}

try {
    Write-Step "Checking server publish prerequisites"
    Assert-Command "ssh"
    Assert-Command "scp"
    Assert-Command "powershell"

    if (-not (Test-Path $SshKey)) {
        throw "SSH key was not found: $SshKey"
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
    $remoteVersionDir = "$remoteRootClean/$releaseVersion"
    $remoteTmpDir = "$remoteRootClean/.upload-$releaseVersion-$(Get-Date -Format yyyyMMddHHmmss)"

    Write-Step "Preparing remote release directories"
    Invoke-Ssh "mkdir -p '$remoteTmpDir' '$remoteVersionDir'"

    Write-Step "Uploading versioned artifacts to server"
    foreach ($artifact in $manifest.artifacts) {
        $artifactPath = [string]$artifact.path
        if (-not (Test-Path $artifactPath)) {
            throw "Artifact listed in manifest was not found: $artifactPath"
        }

        $name = [System.IO.Path]::GetFileName($artifactPath)
        Copy-ToServer -LocalPath $artifactPath -RemotePath "$remoteTmpDir/$name"
    }

    Invoke-Ssh "cp -f '$remoteTmpDir'/* '$remoteVersionDir'/ && rm -rf '$remoteTmpDir'"

    Write-Step "Publishing latest.json last"
    Copy-ToServer -LocalPath $latestJsonPath -RemotePath "$remoteRootClean/latest.json.tmp"
    Invoke-Ssh "mv -f '$remoteRootClean/latest.json.tmp' '$remoteRootClean/latest.json' && chmod -R a+r '$remoteVersionDir' '$remoteRootClean/latest.json'"

    $websiteDir = Join-Path $projectRoot "website"
    $websiteIndexPath = Join-Path $websiteDir "index.html"
    $websiteFaviconPath = Join-Path $websiteDir "favicon.ico"
    $websiteAssetsDir = Join-Path $websiteDir "assets"

    if (Test-Path $websiteIndexPath) {
        Write-Step "Publishing website files"
        Invoke-Ssh "mkdir -p '$remoteRootClean/assets'"

        Copy-ToServer -LocalPath $websiteIndexPath -RemotePath "$remoteRootClean/index.html.tmp"
        Invoke-Ssh "mv -f '$remoteRootClean/index.html.tmp' '$remoteRootClean/index.html' && chmod a+r '$remoteRootClean/index.html'"

        if (Test-Path $websiteFaviconPath) {
            Copy-ToServer -LocalPath $websiteFaviconPath -RemotePath "$remoteRootClean/favicon.ico"
        }

        if (Test-Path $websiteAssetsDir) {
            foreach ($asset in Get-ChildItem -Path $websiteAssetsDir -File) {
                Copy-ToServer -LocalPath $asset.FullName -RemotePath "$remoteRootClean/assets/$($asset.Name)"
            }
        }

        Invoke-Ssh "chmod -R a+r '$remoteRootClean/assets' '$remoteRootClean/favicon.ico' 2>/dev/null || true"
    }

    $cfUpdateBaseUrlClean = $CfUpdateBaseUrl.TrimEnd("/")
    $setupExeArtifact = @($manifest.artifacts) | Where-Object {
        $name = [string]$_.name
        $name -like "*.exe" -and $name -notlike "*.nsis.zip*"
    } | Select-Object -First 1
    $cfManifestUrl = "$cfUpdateBaseUrlClean/latest.json"
    $cfPackageUrl = $null
    if ($setupExeArtifact) {
        $encodedSetupExeName = [System.Uri]::EscapeDataString([string]$setupExeArtifact.name)
        $cfPackageUrl = "$cfUpdateBaseUrlClean/$releaseVersion/$encodedSetupExeName"
    }

    if (-not $SkipPurge) {
        $zoneId = [System.Environment]::GetEnvironmentVariable("HUGESCREENSHOT_CF_ZONE_ID")
        if (-not $zoneId) {
            $zoneId = [System.Environment]::GetEnvironmentVariable("CF_ZONE_ID")
        }

        $apiToken = [System.Environment]::GetEnvironmentVariable("HUGESCREENSHOT_CF_API_TOKEN")
        if (-not $apiToken) {
            $apiToken = [System.Environment]::GetEnvironmentVariable("CF_API_TOKEN")
        }

        $cfEmail = [System.Environment]::GetEnvironmentVariable("CF_EMAIL")
        if (-not $cfEmail) {
            $cfEmail = [System.Environment]::GetEnvironmentVariable("CF_AUTH_EMAIL")
        }
        $cfApiKey = [System.Environment]::GetEnvironmentVariable("CF_API_KEY")

        if ($zoneId -and ($apiToken -or ($cfEmail -and $cfApiKey))) {
            Write-Step "Purging Cloudflare cache"
            $purgeUrls = @($cfManifestUrl)
            if ($cfPackageUrl) {
                $purgeUrls += $cfPackageUrl
            }
            $body = @{ files = $purgeUrls } | ConvertTo-Json -Depth 4

            if ($apiToken) {
                $cfHeaders = @{
                    Authorization = "Bearer $apiToken"
                    "Content-Type" = "application/json"
                }
            }
            else {
                $cfHeaders = @{
                    "X-Auth-Email" = $cfEmail
                    "X-Auth-Key" = $cfApiKey
                    "Content-Type" = "application/json"
                }
            }

            $resp = Invoke-RestMethod `
                -Uri "https://api.cloudflare.com/client/v4/zones/$zoneId/purge_cache" `
                -Method POST `
                -Headers $cfHeaders `
                -Body $body

            if (-not $resp.success) {
                throw "Cloudflare purge failed: $(($resp.errors | ConvertTo-Json -Depth 4))"
            }
            Write-Host "Purge completed: $($purgeUrls -join ', ')"
        }
        else {
            Write-Warning "Skipped Cloudflare purge: set HUGESCREENSHOT_CF_ZONE_ID/CF_ZONE_ID and HUGESCREENSHOT_CF_API_TOKEN/CF_API_TOKEN (or CF_EMAIL + CF_API_KEY)."
        }
    }

    if (-not $SkipPrefetch -and $cfPackageUrl) {
        Write-Step "Prefetching Cloudflare cache"
        $encodedCfPackageUrl = $cfPackageUrl
        $prefetchScript = @'
for i in 1 2 3; do
  curl -sk --max-time 90 -o /dev/null \
    -D /tmp/hugescreenshot-cf-prefetch-headers.txt \
    -w "    GET #$i: http=%{http_code} size=%{size_download}B time=%{time_total}s speed=%{speed_download}B/s\n" \
    "__CF_PKG_URL__"
  status=$(grep -i '^cf-cache-status:' /tmp/hugescreenshot-cf-prefetch-headers.txt | tr -d '\r' | awk '{print $2}')
  ray=$(grep -i '^cf-ray:' /tmp/hugescreenshot-cf-prefetch-headers.txt | tr -d '\r' | awk '{print $2}')
  echo "       cf-cache-status=$status cf-ray=$ray"
  if [ "$status" = "HIT" ]; then
    echo "    Cloudflare edge cache warmed"
    break
  fi
  sleep 1
done
curl -sk --max-time 30 -o /dev/null \
  -D /tmp/hugescreenshot-cf-prefetch-headers.txt \
  "__CF_MANIFEST_URL__"
manifest_status=$(grep -i '^cf-cache-status:' /tmp/hugescreenshot-cf-prefetch-headers.txt | tr -d '\r' | awk '{print $2}')
echo "    manifest cache=$manifest_status"
rm -f /tmp/hugescreenshot-cf-prefetch-headers.txt
'@
        $prefetchScript = $prefetchScript.Replace('__CF_PKG_URL__', $encodedCfPackageUrl)
        $prefetchScript = $prefetchScript.Replace('__CF_MANIFEST_URL__', $cfManifestUrl)

        # 经管道喂给远程 bash 时，PowerShell 可能在脚本首部加 UTF-8 BOM，导致远程 bash 语法报错。
        # 远程先用 tr 删除 BOM 字节(EF BB BF = 八进制 357 273 277)再交给 bash；脚本为纯 ASCII，无副作用。
        $prefetchScript | & ssh -i "$SshKey" -p $SshPort -o ConnectTimeout=15 "$SshUser@$SshHost" "tr -d '\357\273\277' | bash -s"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "SSH prefetch failed; first user download may be a Cloudflare MISS."
        }

        if (Get-Command "curl.exe" -ErrorAction SilentlyContinue) {
            Write-Host "Local Cloudflare HEAD check:"
            $localHead = & curl.exe -sIk --max-time 15 "$encodedCfPackageUrl" 2>$null
            $localHead | Select-String -Pattern '^(HTTP|CF-Cache-Status|CF-Ray|Age|Content-Length|X-HuGe-Cache):' | ForEach-Object {
                Write-Host "  $($_.Line.Trim())"
            }
        }
    }

    Write-Step "Server publish completed"
    Write-Host "Version      : $releaseVersion" -ForegroundColor Green
    Write-Host "Host         : $SshUser@$SshHost`:$SshPort"
    Write-Host "Remote root  : $remoteRootClean"
    Write-Host "Origin JSON  : $($ReleaseBaseUrl.TrimEnd('/'))/latest.json"
    Write-Host "Worker JSON  : $cfManifestUrl"
}
finally {
    # no-op
}
