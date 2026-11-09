#!/usr/bin/env bash
# Start the API on :8000 and both storefronts (:5180, :5181). Logs and PIDs go to .run/.
# Services that are already running are left alone. A healthy Postgres container is never touched;
# a stopped or missing one is started only with your approval (see ensure_postgres in _common.sh).
# Restart only the API with scripts/restart_api.sh. Stop with scripts/stop.sh.
source "$(dirname "$0")/_common.sh"
cd "$ROOT"
mkdir -p "$RUN_DIR"

[ -f .env ] || { echo "!! .env missing. Run scripts/setup.sh first." >&2; exit 1; }
(cd backend && "$VENV/bin/python" -m app.config) || { echo "!! Configuration check failed; nothing was started." >&2; exit 1; }

ensure_postgres || { echo "!! Postgres is not available; the API and storefronts were not started." >&2; exit 1; }

if curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "Ollama: running"
else
  echo "Ollama: NOT running — the assistant will use rule-based replies. Start it with: ollama serve (or open the Ollama app)"
fi

FAILED=0
start_bg() { # name, port, dir, command...
  local name=$1 port=$2 dir=$3; shift 3
  local pidfile="$RUN_DIR/$name.pid" holder
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "$name: already running (PID $(cat "$pidfile"))"; return 0
  fi
  holder=$(listener_pid "$port")
  if [ -n "$holder" ]; then
    # Something already serves this port (e.g. started by hand): never start a second copy or kill it.
    echo "$name: port $port is already in use by PID $holder ($(ps -o comm= -p "$holder" 2>/dev/null || echo '?')); left as is"
    return 0
  fi
  # cd first, then background only the server itself so $! is its real PID and no shell keeps our stdout open.
  (cd "$dir" || exit 1; nohup "$@" </dev/null >"$RUN_DIR/$name.log" 2>&1 & echo $! >"$pidfile")
  local pid i
  pid=$(cat "$pidfile")
  for ((i = 0; i < 40; i++)); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "!! $name exited during startup. Last log lines (.run/$name.log):" >&2
      tail -n 15 "$RUN_DIR/$name.log" >&2 || true
      rm -f "$pidfile"; FAILED=1; return 0
    fi
    [ -n "$(listener_pid "$port")" ] && { echo "$name: started (PID $pid, log: .run/$name.log)"; return 0; }
    sleep 0.5
  done
  echo "!! $name (PID $pid) is running but not listening on port $port after 20s. See .run/$name.log" >&2
  FAILED=1
}

start_bg api 8000 backend "$VENV/bin/uvicorn" app.main:build_app --factory --host 127.0.0.1 --port 8000
start_bg store-a 5180 frontend npm run dev -w store-a
start_bg store-b 5181 frontend npm run dev -w store-b

for ((i = 0; i < 20; i++)); do curl -s -m 1 http://127.0.0.1:8000/api/health >/dev/null && break; sleep 0.5; done
echo
echo "API health:  $(curl -s -m 5 http://127.0.0.1:8000/api/health || echo unavailable)"
echo "Store A:     http://127.0.0.1:5180   (Summit Trail Co.)"
echo "Store B:     http://127.0.0.1:5181   (Bloom & Brew)"
echo "API docs:    http://127.0.0.1:8000/docs"
[ "$FAILED" = 0 ] || { echo "!! One or more services failed to start (see above)." >&2; exit 1; }
