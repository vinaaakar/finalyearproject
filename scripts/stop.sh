#!/usr/bin/env bash
# Stop the processes started by start.sh. Pass --db to also stop (not delete) the Postgres container.
source "$(dirname "$0")/_common.sh"
cd "$ROOT"
for name in store-b store-a api; do
  f="$RUN_DIR/$name.pid"
  if [ -f "$f" ]; then
    pid=$(cat "$f")
    pkill -TERM -P "$pid" 2>/dev/null || true
    kill "$pid" 2>/dev/null && echo "$name: stopped" || echo "$name: not running"
    rm -f "$f"
  fi
done
if [ "${1:-}" = "--db" ]; then docker compose stop postgres; fi
