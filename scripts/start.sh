#!/usr/bin/env bash
# Start Postgres (if stopped), the API on :8000 and both storefronts (:5180, :5181).
# Logs and PIDs go to .run/. Stop with scripts/stop.sh.
source "$(dirname "$0")/_common.sh"
cd "$ROOT"
mkdir -p "$RUN_DIR"

[ -f .env ] || { echo "!! .env missing. Run scripts/setup.sh first." >&2; exit 1; }
(cd backend && "$VENV/bin/python" -m app.config) || exit 1

docker compose up -d postgres >/dev/null
for i in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' avc_postgres 2>/dev/null)" = "healthy" ] && break; sleep 1
done

if curl -s -m 2 http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "Ollama: running"
else
  echo "Ollama: NOT running — the assistant will use rule-based replies. Start it with: ollama serve (or open the Ollama app)"
fi

start_bg() { # name, dir, command...
  local name=$1 dir=$2; shift 2
  if [ -f "$RUN_DIR/$name.pid" ] && kill -0 "$(cat "$RUN_DIR/$name.pid")" 2>/dev/null; then
    echo "$name: already running"; return
  fi
  # cd first, then background only the server itself so $! is its real PID and no shell keeps our stdout open.
  (cd "$dir" || exit 1; nohup "$@" </dev/null >"$RUN_DIR/$name.log" 2>&1 & echo $! >"$RUN_DIR/$name.pid")
  echo "$name: started (log: .run/$name.log)"
}

start_bg api backend "$VENV/bin/uvicorn" app.main:build_app --factory --host 127.0.0.1 --port 8000
start_bg store-a frontend npm run dev -w store-a
start_bg store-b frontend npm run dev -w store-b

for i in $(seq 1 20); do curl -s -m 1 http://127.0.0.1:8000/api/health >/dev/null && break; sleep 0.5; done
echo
echo "API health:  $(curl -s -m 5 http://127.0.0.1:8000/api/health || echo unavailable)"
echo "Store A:     http://127.0.0.1:5180   (Summit Trail Co.)"
echo "Store B:     http://127.0.0.1:5181   (Bloom & Brew)"
echo "API docs:    http://127.0.0.1:8000/docs"
