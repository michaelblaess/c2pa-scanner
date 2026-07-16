#Requires -Version 5.1
<#
.SYNOPSIS
    Richtet die Dev-Umgebung ein (uv sync + dev-Tools).
.DESCRIPTION
    Hinter dem Corporate-Proxy (Zscaler) nutzt uv den Windows-Zertifikatspeicher
    via --native-tls; SSL_CERT_FILE wird geleert, weil rustls das Bundle ablehnt.
#>
$ErrorActionPreference = "Stop"

$env:SSL_CERT_FILE = $null
$env:REQUESTS_CA_BUNDLE = $null

Write-Host "uv sync (--extra dev, --native-tls)..." -ForegroundColor Cyan
uv sync --extra dev --native-tls
if ($LASTEXITCODE -ne 0) { throw "uv sync fehlgeschlagen" }

Write-Host "Playwright Chromium..." -ForegroundColor Cyan
uv run playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "playwright install fehlgeschlagen" }

Write-Host "Fertig. Start: ./run.ps1 scan <sitemap-url>" -ForegroundColor Green
