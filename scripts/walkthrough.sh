#!/usr/bin/env bash
# One clean dev server, browser opened, walkthrough already running.
#
#   make walkthrough                 # prewarm: refusal, research, real kit  (~3 min)
#   make walkthrough PHASE=onstage   # injection blocked, real cart          (~25 s)
#   make walkthrough PHASE=all       # everything, for rehearsal
#
# Everything is live. CONCIERGE_FIXTURE_MODE is the fake and the page says so.
set -u

cd "$(dirname "$0")/.." || exit 1

PHASE="${1:-prewarm}"
case "$PHASE" in
  prewarm | onstage | all) ;;
  *)
    echo "unknown phase '$PHASE' — expected prewarm, onstage or all" >&2
    exit 2
    ;;
esac

LOG=.reflex-walkthrough.log
URL="http://localhost:3000/?walkthrough=${PHASE}"

# Two patterns, not one: the frontend is a detached `react-router dev` node process
# under .web/ that outlives the reflex supervisor and keeps holding port 3000.
# Never inline a pkill for 'reflex run' — the pattern matches the calling shell's own
# command line and kills the caller.
pkill -9 -f 'bin/reflex' 2>/dev/null
pkill -9 -f '\.web/node_modules/\.bin/react-router' 2>/dev/null
sleep 2

if ss -ltn 2>/dev/null | grep -qE ':(3000|8000)[[:space:]]'; then
  echo "Ports 3000/8000 are still held, and Reflex needs both pinned:" >&2
  ss -ltnp 2>/dev/null | grep -E ':(3000|8000)[[:space:]]' >&2
  exit 1
fi

: >"$LOG"
./.venv/bin/reflex run >>"$LOG" 2>&1 &
REFLEX_PID=$!
trap 'kill "$REFLEX_PID" 2>/dev/null' INT TERM EXIT

printf 'compiling'
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
  echo "the dev server never came up:" >&2
  tail -25 "$LOG" >&2
  exit 1
fi

command -v xdg-open >/dev/null 2>&1 && (xdg-open "$URL" >/dev/null 2>&1 &)

cat <<EOF
  $URL

  The walkthrough starts on its own — the query parameter is what triggers it, so a
  plain visit to localhost:3000 will not restart it and wipe the kit.

    prewarm   swim refusal, grounded research, real 10-item kit      ~3 min
    onstage   injection blocked with prices unmoved, then the cart   ~25 s

  Run prewarm while the pitch is still on the problem statement, then click
  "2 · Go live" when the audience is looking. Ctrl-C stops the server.
EOF

wait "$REFLEX_PID"
