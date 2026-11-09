#!/usr/bin/env bash
# Handytest im selben WLAN ohne Caddy (nur Linux-Entwicklungsrechner):
#   ./deploy/start-lan-test.sh            → https://<LAN-IP>:8443/melder/
# Erzeugt einmalig eine lokale CA + Serverzertifikat in data/tls/ und startet uvicorn direkt mit TLS.
# Nicht für den Einsatz: dort läuft uvicorn nur auf 127.0.0.1 hinter Caddy (deploy/Caddyfile).
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
port="${MELDI_PORT:-8443}"
tls="$root/data/tls"
ips="$(ip -4 -o addr show scope global | awk '{split($4,a,"/"); print a[1]}')"

(cd "$root/frontend" && { [ -d node_modules ] || npm ci; } && npm run build)
(cd "$root/backend" && uv sync --all-groups && uv run meldi demo)

mkdir -p "$tls"
if [ ! -f "$tls/ca.crt" ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 825 -subj "/CN=Meldi Test-CA" \
    -addext "basicConstraints=critical,CA:TRUE" -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -keyout "$tls/ca.key" -out "$tls/ca.crt" 2>/dev/null
fi
# Serverzertifikat bei jedem Start neu, damit es zu den aktuellen IPs passt
san="DNS:localhost,IP:127.0.0.1$(for ip in $ips; do printf ',IP:%s' "$ip"; done)"
openssl req -newkey rsa:2048 -nodes -subj "/CN=meldi" -keyout "$tls/server.key" -out "$tls/server.csr" 2>/dev/null
openssl x509 -req -in "$tls/server.csr" -CA "$tls/ca.crt" -CAkey "$tls/ca.key" -CAcreateserial -days 365 \
  -extfile <(printf 'subjectAltName=%s\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE' "$san") \
  -out "$tls/server.crt" 2>/dev/null

# Wie im Einsatz: Modell nur lokal laden, keine Anfrage an huggingface.co
export MELDI_STT_LOCAL_FILES_ONLY=true HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1

echo
for ip in $ips; do echo "Melder:  https://$ip:$port/melder/"; done
echo "ELW:     https://localhost:$port/elw/"
echo "CA-Zertifikat fürs Handy: $tls/ca.crt"
echo
cd "$root/backend" && exec uv run uvicorn --factory app.main:create_app --host 0.0.0.0 --port "$port" \
  --ssl-keyfile "$tls/server.key" --ssl-certfile "$tls/server.crt"
