#Requires -Version 5.1
<#
.SYNOPSIS
    Compiles c2pa-scanner into a standalone Windows binary with Nuitka.
.DESCRIPTION
    Self-contained --standalone build (no Python install needed on the target).
    Bundles a Chromium headless shell into dist\c2pa-scanner\browsers\, so the
    --render mode works without a separate Playwright install. __main__.py points
    PLAYWRIGHT_BROWSERS_PATH at that folder when running as a compiled binary.

    Output: dist\c2pa-scanner\c2pa-scanner.exe plus its DLLs and browsers\, and
    dist\c2pa-scanner-vX.Y.Z-windows-x64.zip to hand out.
#>

$ErrorActionPreference = "Stop"

$root    = $PSScriptRoot
$entry   = Join-Path $root "src\c2pa_scanner\__main__.py"
$initPy  = Join-Path $root "src\c2pa_scanner\__init__.py"
$outDir  = Join-Path $root "dist"
$distDir = Join-Path $outDir "c2pa-scanner"

# venv mit dem Lockfile abgleichen - VOR der python-Ermittlung, damit .venv auch
# bei einem frischen Checkout (CI) existiert. --inexact laesst ad-hoc nuitka stehen.
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Syncing venv (uv sync --inexact)..." -ForegroundColor Cyan
    & uv sync --inexact --project $root
    if ($LASTEXITCODE -ne 0) { throw "uv sync fehlgeschlagen" }
}

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

Write-Host "Checking Playwright Chromium..." -ForegroundColor Cyan
& $python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "playwright install fehlgeschlagen" }

$version = ([regex]'__version__\s*=\s*"([^"]+)"').Match((Get-Content -Raw $initPy)).Groups[1].Value
if (-not $version) { throw "Konnte __version__ nicht aus $initPy lesen" }

Write-Host "Compiling c2pa-scanner v$version with Nuitka..." -ForegroundColor Cyan
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
$started = Get-Date

# --include-package=c2pa: das Rust-Wheel wird lazy importiert - explizit mitnehmen.
$nuitkaArgs = @(
    "--standalone"
    "--assume-yes-for-downloads"
    "--remove-output"
    "--include-package=c2pa_scanner"
    "--include-package-data=c2pa_scanner"
    "--include-package=c2pa"
    "--output-dir=$outDir"
    "--output-filename=c2pa-scanner.exe"
    "--company-name=Michael Blaess"
    "--product-name=c2pa-scanner"
    "--file-version=$version"
    "--product-version=$version"
)

$iconPath = Join-Path $root "assets\icon.ico"
if (Test-Path $iconPath) {
    $nuitkaArgs += "--windows-icon-from-ico=$iconPath"
} else {
    Write-Host "Hinweis: $iconPath fehlt - EXE wird ohne Icon gebaut." -ForegroundColor Yellow
}

& $python -m nuitka --version 2>$null 1>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka fehlt im venv - installiere..." -ForegroundColor Yellow
    & uv pip install nuitka
    if ($LASTEXITCODE -ne 0) { throw "Nuitka-Installation fehlgeschlagen" }
}

& $python -m nuitka @nuitkaArgs $entry
if ($LASTEXITCODE -ne 0) { throw "Nuitka-Build fehlgeschlagen (Exit $LASTEXITCODE)" }

# Nuitka benennt den dist-Ordner nach dem Hauptmodul (__main__.dist) - umbenennen
$nuitkaDist = Join-Path $outDir "__main__.dist"
if (Test-Path $nuitkaDist) { Rename-Item -Path $nuitkaDist -NewName "c2pa-scanner" }

# Chromium headless shell aus dem Playwright-Cache in dist\...\browsers\ kopieren.
Write-Host "Bundling Chromium headless shell..." -ForegroundColor Cyan
$browsersDir = Join-Path $distDir "browsers"
New-Item -ItemType Directory -Path $browsersDir -Force | Out-Null
$cache = Join-Path $env:LOCALAPPDATA "ms-playwright"
$latest = Get-ChildItem -Path $cache -Directory -Filter "chromium_headless_shell-*" |
    Sort-Object { [int]($_.Name -replace '.*-', '') } -Descending |
    Select-Object -First 1
if (-not $latest) { throw "Kein chromium_headless_shell im Playwright-Cache gefunden" }
Copy-Item -Recurse -Force $latest.FullName (Join-Path $browsersDir $latest.Name)

$elapsed = [int]((Get-Date) - $started).TotalSeconds
$exe     = Join-Path $distDir "c2pa-scanner.exe"
$sizeMB  = [math]::Round(((Get-ChildItem -Recurse $distDir | Measure-Object Length -Sum).Sum) / 1MB, 1)

$zip = Join-Path $outDir "c2pa-scanner-v$version-windows-x64.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $distDir -DestinationPath $zip
$zipMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)

Write-Host ""
Write-Host "Done in ${elapsed}s" -ForegroundColor Green
Write-Host "  dist folder : $distDir  (${sizeMB} MB)"
Write-Host "  zip         : $zip  (${zipMB} MB)"
Write-Host "  run         : $exe"
