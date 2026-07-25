#!/usr/bin/env bash
# Encodes the §9.2 ordering trap: api_url is compiled INTO the frontend bundle,
# so the BACKEND tunnel must exist before reflex compiles. Wrong order gives a
# page that renders perfectly and does nothing at all.
set -euo pipefail
cd "$(dirname "$0")/.."

CF=./bin/cloudflared
LOG=.tunnel
mkdir -p "$LOG"

grab_url() {  # $1 = logfile
  for _ in $(seq 1 60); do
    u=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$1" | head -1 || true)
    [ -n "$u" ] && { echo "$u"; return 0; }
    sleep 1
  done
  return 1
}

pkill -f 'cloudflared tunnel --url' 2>/dev/null || true

# A dev server already on :3000 is the silent killer here. Step 2's `reflex run`
# would fail to bind, step 2's curl check would be answered by the OLD server —
# still compiled against http://localhost:8000 — and the frontend tunnel would
# happily serve that stale bundle. The judge URL then renders and does nothing,
# which is the exact failure this script exists to prevent.
# Two patterns: the frontend is a detached `react-router dev` node process under
# .web/ that outlives the reflex supervisor and keeps holding :3000.
pkill -9 -f 'bin/reflex' 2>/dev/null || true
pkill -9 -f '\.web/node_modules/\.bin/react-router' 2>/dev/null || true
sleep 2
if ss -ltn 2>/dev/null | grep -qE ':(3000|8000)[[:space:]]'; then
  echo "ports 3000/8000 still held — reflex needs both, and a stale bundle would be served:"
  ss -ltnp 2>/dev/null | grep -E ':(3000|8000)[[:space:]]'
  exit 1
fi

echo "1/4  backend tunnel (:8000) — needed BEFORE reflex compiles"
$CF tunnel --url http://localhost:8000 --no-autoupdate >"$LOG/backend.log" 2>&1 &
BACKEND=$(grab_url "$LOG/backend.log") || { echo "backend tunnel failed"; exit 1; }
echo "     $BACKEND"

echo "2/4  reflex run, compiled against that api_url"
CONCIERGE_API_URL="$BACKEND" ./.venv/bin/reflex run >"$LOG/reflex.log" 2>&1 &
for _ in $(seq 1 180); do
  curl -sf http://localhost:3000 >/dev/null 2>&1 && break
  sleep 1
done

echo "3/4  frontend tunnel (:3000)"
$CF tunnel --url http://localhost:3000 --no-autoupdate >"$LOG/frontend.log" 2>&1 &
FRONTEND=$(grab_url "$LOG/frontend.log") || { echo "frontend tunnel failed"; exit 1; }

echo "$BACKEND"  > "$LOG/backend.url"
echo "$FRONTEND" > "$LOG/frontend.url"

cat <<EOF

4/4  ===================== JUDGE URL =====================
     $FRONTEND
     backend: $BACKEND
     =====================================================

  PROVE IT from a phone, not this laptop. Open the judge URL and send one
  message. A reply is the only positive proof the WebSocket reached the
  tunnelled backend. Silence means api_url is stale — rerun this script.

  Leave both tunnels up. If the backend tunnel dies its URL changes and the
  compiled bundle is stale, so the whole sequence must be redone.
EOF
