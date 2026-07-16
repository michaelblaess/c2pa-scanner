#!/usr/bin/env bash
# Richtet die Dev-Umgebung ein (uv sync + dev-Tools).
# Hinter TLS-aufbrechenden Proxies nutzt uv den System-Truststore via --native-tls.
set -euo pipefail

unset SSL_CERT_FILE REQUESTS_CA_BUNDLE 2>/dev/null || true

echo "uv sync (--extra dev, --native-tls)..."
uv sync --extra dev --native-tls

echo "Fertig. Start: ./run.sh scan <ordner>"
