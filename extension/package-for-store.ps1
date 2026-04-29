# Build a Chrome Web Store–ready .zip of the extension (root of the zip = extension root).
# Run from the extension folder:
#   powershell -ExecutionPolicy Bypass -File .\package-for-store.ps1
# Output: extension/dist/manga-watchlist-companion-v<version>.zip

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$manifestPath = Join-Path $root "manifest.json"
if (-not (Test-Path $manifestPath)) {
  Write-Error "Run this script from the extension/ directory (manifest.json not found)."
}
$version = (Get-Content $manifestPath -Raw | ConvertFrom-Json).version
if (-not $version) { $version = "0.0.0" }

$dist = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $dist | Out-Null
$zipName = "manga-watchlist-companion-v$version.zip"
$zipPath = Join-Path $dist $zipName
if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

$staging = Join-Path $env:TEMP "mt-chrome-ext-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Force -Path $staging | Out-Null
try {
  $files = @(
    "manifest.json",
    "config.js",
    "background.js",
    "content.js",
    "popup.html",
    "popup.js",
    "options.html",
    "options.js"
  )
  foreach ($f in $files) {
    Copy-Item (Join-Path $root $f) (Join-Path $staging $f) -Force
  }
  $iconsDest = Join-Path $staging "icons"
  New-Item -ItemType Directory -Force -Path $iconsDest | Out-Null
  Get-ChildItem (Join-Path $root "icons") -Filter "*.png" | ForEach-Object {
    Copy-Item $_.FullName (Join-Path $iconsDest $_.Name) -Force
  }

  Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force
  Write-Host "Wrote $zipPath"
  Write-Host "Upload this zip at https://chrome.google.com/webstore/devconsole"
} finally {
  Remove-Item -Recurse -Force $staging -ErrorAction SilentlyContinue
}
