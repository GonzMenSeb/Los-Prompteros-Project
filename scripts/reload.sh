#!/usr/bin/env bash
# Restart the dev server WITHOUT changing the judge URL.
#
# Use after editing .env (new API keys, VIP token) or any Python module, when a QR code
# is already in the wild. `api_url` is compiled INTO the frontend bundle, so we
# recompile against the SAME backend tunnel URL that is already running; both
# cloudflared processes stay up and reattach to the ports when they come back.
#
# `make tunnel` would mint NEW tunnel URLs and invalidate the QR code. This does not.
set -u

cd "$(dirname "$0")/.." || exit 1

if [ ! -s .tunnel/backend.url ]; then
  echo "no .tunnel/backend.url — nothing to preserve. Use 'make tunnel' first." >&2
  exit 1
fi
BACKEND=$(cat .tunnel/backend.url)
FRONTEND=$(cat .tunnel/frontend.url 2>/dev/null || echo '(unknown)')

if ! pgrep -f 'cloudflared tunnel --url' >/dev/null 2>&1; then
  echo "the cloudflared tunnels are gone, so their URLs are already dead." >&2
  echo "run 'make tunnel' and redo the QR code." >&2
  exit 1
fi

# Two patterns: the frontend is a detached `react-router dev` node process under .web/
# that outlives the reflex supervisor and keeps holding :3000. Never inline a pkill for
# 'reflex run' — the pattern matches the calling shell and kills the caller.
pkill -9 -f 'bin/reflex' 2>/dev/null
pkill -9 -f '\.web/node_modules/\.bin/react-router' 2>/dev/null
sleep 2

LOG=.tunnel/reflex.log
: >"$LOG"
CONCIERGE_API_URL="$BACKEND" ./.venv/bin/reflex run >>"$LOG" 2>&1 &
REFLEX_PID=$!

printf 'recompiling against %s' "$BACKEND"
ready=""
for _ in $(seq 1 150); do
  if grep -q 'App running at' "$LOG" 2>/dev/null; then ready=1; break; fi
  if grep -qiE 'already in use|Traceback' "$LOG" 2>/dev/null; then break; fi
  kill -0 "$REFLEX_PID" 2>/dev/null || break
  printf '.'
  sleep 2
done
echo

if [ -z "$ready" ]; then
  echo "the dev server did not come back:" >&2
  tail -25 "$LOG" >&2
  exit 1
fi

cat <<EOF
  same judge URL, still valid: $FRONTEND

  Reload the page in any browser that already had it open — the bundle changed.
EOF
