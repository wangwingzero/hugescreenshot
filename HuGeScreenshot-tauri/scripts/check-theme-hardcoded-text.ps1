param(
  [string]$Root = "src/components"
)

$ErrorActionPreference = "Stop"

$patterns = @(
  "color:\s*white\b",
  "color:\s*#fff\b",
  "color:\s*#ffffff\b",
  "color:\s*rgba\(\s*255\s*,\s*255\s*,\s*255\s*,",
  "border-top-color:\s*white\b",
  "border-top-color:\s*#fff\b",
  "border-top-color:\s*#ffffff\b",
  "var\(--text-(primary|secondary|muted)\s*,\s*rgba\(\s*255\s*,\s*255\s*,\s*255\s*,"
)

$regex = [string]::Join("|", $patterns)
$files = Get-ChildItem -Path $Root -Recurse -Filter "*.vue"
$matches = @()

foreach ($file in $files) {
  $hits = Select-String -Path $file.FullName -Pattern $regex
  foreach ($hit in $hits) {
    $matches += "$($hit.Path):$($hit.LineNumber): $($hit.Line.Trim())"
  }
}

if ($matches.Count -gt 0) {
  Write-Host "Found hardcoded light-theme-risk text colors:" -ForegroundColor Yellow
  $matches | ForEach-Object { Write-Host $_ }
  exit 1
}

Write-Host "No hardcoded risky text colors found in $Root." -ForegroundColor Green
exit 0
