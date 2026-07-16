#Requires -Version 5.1
# Startet c2pa-scanner aus dem Quellcode.
$ErrorActionPreference = "Stop"
$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }
& $python -m c2pa_scanner @args
