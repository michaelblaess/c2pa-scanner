#!/usr/bin/env bash
# compile-linux.sh - compiles c2pa-scanner into a standalone Linux binary with
# Nuitka, with a bundled Chromium headless shell (for the --render mode).
#
# Output: dist/c2pa-scanner/c2pa-scanner + browsers/, and
# dist/c2pa-scanner-vX.Y.Z-linux-x86_64.tar.gz ready to hand out.
#
# Build machine needs: gcc, patchelf, Python headers
#   Debian/Ubuntu:  sudo apt install gcc patchelf python3-dev

set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
entry="$root/src/c2pa_scanner/__main__.py"
init_py="$root/src/c2pa_scanner/__init__.py"
out_dir="$root/dist"
dist_dir="$out_dir/c2pa-scanner"

for tool in gcc patchelf; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        echo "Fehlt: $tool - bitte installieren (z.B. sudo apt install gcc patchelf python3-dev)" >&2
        exit 1
    fi
done

# venv mit dem Lockfile abgleichen - VOR der python-Ermittlung, damit .venv auch
# bei einem frischen Checkout (CI) existiert. --inexact laesst ad-hoc nuitka stehen.
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

echo "Compiling c2pa-scanner v$version with Nuitka..."
rm -rf "$dist_dir"
started=$(date +%s)

# Nuitka als Build-Tool sicherstellen (kein Dev-Dep, wird ad-hoc installiert).
if ! "$python" -m nuitka --version >/dev/null 2>&1; then
    echo "Nuitka fehlt im venv - installiere..."
    uv pip install nuitka || { echo "Nuitka-Installation fehlgeschlagen" >&2; exit 1; }
fi

# --include-package=c2pa: das Rust-Wheel wird lazy importiert (from c2pa import
# Reader) - explizit einschliessen, damit Nuitka die Extension sicher mitnimmt.
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

# Chromium headless shell mitbuendeln (~113 MB) - der --render-Modus laeuft
# headless. __main__.py zeigt PLAYWRIGHT_BROWSERS_PATH auf diesen Ordner, wenn
# es als kompiliertes Binary laeuft (Nuitka __compiled__).
echo "Bundling Chromium headless shell..."
browsers_dir="$dist_dir/browsers"
mkdir -p "$browsers_dir"
cache="${HOME}/.cache/ms-playwright"
latest="$(ls -d "$cache/chromium_headless_shell-"* 2>/dev/null | sort -V | tail -1)"
if [ ! -d "$latest" ]; then
    echo "Kein chromium_headless_shell im Playwright-Cache gefunden" >&2
    exit 1
fi
cp -r "$latest" "$browsers_dir/"

elapsed=$(( $(date +%s) - started ))
size_mb=$(du -sm "$dist_dir" | cut -f1)

tarball="$out_dir/c2pa-scanner-v$version-linux-x86_64.tar.gz"
rm -f "$tarball"
tar -czf "$tarball" -C "$out_dir" c2pa-scanner
tar_mb=$(du -sm "$tarball" | cut -f1)

echo ""
echo "Done in ${elapsed}s"
echo "  dist folder : $dist_dir  (${size_mb} MB)"
echo "  tarball     : $tarball  (${tar_mb} MB)"
