#!/usr/bin/env bash
# Meldi lokal starten (Linux, Entwicklung/Test):  MELDI_HOST=192.168.8.10 ./deploy/start-dev.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export MELDI_HOST="${MELDI_HOST:-localhost}"

(cd "$root/frontend" && { [ -d node_modules ] || npm ci; } && npm run build)
(cd "$root/backend" && uv sync && uv run meldi demo)

caddy_bin="$(command -v caddy || echo "$root/deploy/bin/caddy")"
"$caddy_bin" run --config "$root/deploy/Caddyfile" &
caddy_pid=$!
trap 'kill $caddy_pid 2>/dev/null' EXIT

echo -e "\nMelder:  https://$MELDI_HOST/melder/\nELW:     https://$MELDI_HOST/elw/\n"
cd "$root/backend" && uv run uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8000
