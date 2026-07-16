#!/usr/bin/env bash
# compile-macos.sh - compiles c2pa-scanner into a standalone macOS binary with
# Nuitka, with a bundled Chromium headless shell (for the --render mode).
#
# Output: dist/c2pa-scanner/c2pa-scanner + browsers/, and
# dist/c2pa-scanner-vX.Y.Z-macos-<arch>.tar.gz ready to hand out.
#
# Build machine needs the Xcode Command Line Tools (clang): xcode-select --install
# On download, macOS quarantines the binary - the recipient clears it once:
#   xattr -dr com.apple.quarantine c2pa-scanner
# No .app bundle (this is a TUI). The arch (arm64/x86_64) is host-bound.

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
entry="$root/src/c2pa_scanner/__main__.py"
init_py="$root/src/c2pa_scanner/__init__.py"
out_dir="$root/dist"
dist_dir="$out_dir/c2pa-scanner"
arch="$(uname -m)"   # arm64 (Apple Silicon) oder x86_64 (Intel)

if ! command -v clang >/dev/null 2>&1; then
    echo "Fehlt: clang - bitte Xcode Command Line Tools installieren: xcode-select --install" >&2
    exit 1
fi

if command -v uv >/dev/null 2>&1; then
    echo "Syncing venv (uv sync --inexact)..."
    uv sync --inexact --project "$root"
fi

if [ -x "$root/.venv/bin/python" ]; then
    python="$root/.venv/bin/python"
else
    python="python3"
fi

echo "Checking Playwright Chromium..."
"$python" -m playwright install chromium

version="$(sed -n 's/^__version__ *= *"\([^"]*\)".*/\1/p' "$init_py")"
if [ -z "$version" ]; then
    echo "Konnte __version__ nicht aus $init_py lesen" >&2
    exit 1
fi

echo "Compiling c2pa-scanner v$version ($arch) with Nuitka..."
rm -rf "$dist_dir"
started=$(date +%s)

if ! "$python" -m nuitka --version >/dev/null 2>&1; then
    echo "Nuitka fehlt im venv - installiere..."
    uv pip install nuitka || { echo "Nuitka-Installation fehlgeschlagen" >&2; exit 1; }
fi

"$python" -m nuitka \
    --standalone \
    --assume-yes-for-downloads \
    --remove-output \
    --include-package=c2pa_scanner \
    --include-package-data=c2pa_scanner \
    --include-package=c2pa \
    --output-dir="$out_dir" \
    --output-filename=c2pa-scanner \
    "$entry"

if [ -d "$out_dir/__main__.dist" ]; then
    mv "$out_dir/__main__.dist" "$dist_dir"
fi

echo "Bundling Chromium headless shell..."
browsers_dir="$dist_dir/browsers"
mkdir -p "$browsers_dir"
cache="${HOME}/Library/Caches/ms-playwright"
latest="$(ls -d "$cache/chromium_headless_shell-"* 2>/dev/null | sort -V | tail -1)"
if [ ! -d "$latest" ]; then
    echo "Kein chromium_headless_shell im Playwright-Cache gefunden" >&2
    exit 1
fi
cp -R "$latest" "$browsers_dir/"

elapsed=$(( $(date +%s) - started ))
size_mb=$(du -sm "$dist_dir" | cut -f1)

tarball="$out_dir/c2pa-scanner-v$version-macos-$arch.tar.gz"
rm -f "$tarball"
tar -czf "$tarball" -C "$out_dir" c2pa-scanner
tar_mb=$(du -sm "$tarball" | cut -f1)

echo ""
echo "Done in ${elapsed}s"
echo "  dist folder : $dist_dir  (${size_mb} MB)"
echo "  tarball     : $tarball  (${tar_mb} MB)"
