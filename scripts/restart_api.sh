#!/usr/bin/env bash
# Restart ONLY the API (uvicorn on 127.0.0.1:8000).
#
# This script never runs Docker or Docker Compose, and never stops or starts PostgreSQL, Ollama or either
# storefront. It only signals the process that (a) listens on the API port AND (b) is this project's uvicorn.
#
#   1. preflight: validate .env and import the app BEFORE stopping anything (a broken change can't take the API down)
#   2. identify the running API; refuse if the port is held by any other program
#   3. record the storefront PIDs
#   4. copy .run/api.log to .run/api.log.<timestamp>
#   5. SIGTERM the old API and wait until it has exited and the port is free (no SIGKILL, no second copy)
#   6. launch the new API, then wait until the NEW PID is listening and /api/health answers
#   7. confirm the storefront PIDs are unchanged
#
# Exit codes: 0 healthy · 1 failed (details printed; other services untouched) · 3 running but health "degraded".
# Test hooks (used by scripts/tests): AVC_API_PORT, AVC_STORE_PORTS, AVC_RUN_DIR, AVC_API_CMD, AVC_API_DIR,
# AVC_API_MATCH, AVC_PREFLIGHT_CMD, AVC_STOP_TIMEOUT, AVC_HEALTH_TIMEOUT.
source "$(dirname "$0")/_common.sh"

API_PORT="${AVC_API_PORT:-8000}"
STORE_PORTS="${AVC_STORE_PORTS:-5180 5181}"
RUN="${AVC_RUN_DIR:-$RUN_DIR}"
PIDFILE="$RUN/api.pid"
LOG="$RUN/api.log"
STOP_TIMEOUT="${AVC_STOP_TIMEOUT:-20}"
HEALTH_TIMEOUT="${AVC_HEALTH_TIMEOUT:-40}"
HEALTH_URL="http://127.0.0.1:$API_PORT/api/health"
# How this project's API process is recognised in `ps` output.
API_MATCH="${AVC_API_MATCH:-$VENV/bin/uvicorn app.main:build_app}"
if [ -n "${AVC_API_CMD:-}" ]; then
  read -r -a API_CMD <<<"$AVC_API_CMD"
  API_DIR="${AVC_API_DIR:-$ROOT}"
else
  API_CMD=("$VENV/bin/uvicorn" app.main:build_app --factory --host 127.0.0.1 --port "$API_PORT")
  API_DIR="$ROOT/backend"
fi

fail() { echo "!! $*" >&2; exit 1; }
cmdline() { ps -o command= -p "$1" 2>/dev/null || true; }
store_pids() { local p out=""; for p in $STORE_PORTS; do out="$out$p:$(listener_pid "$p") "; done; echo "${out% }"; }
# Alive and not a zombie (an exited process its parent has not reaped yet still answers `kill -0`).
is_running() {
  kill -0 "$1" 2>/dev/null || return 1
  case "$(ps -o stat= -p "$1" 2>/dev/null)" in Z* | "") return 1 ;; esac
  return 0
}

mkdir -p "$RUN"

# 1. preflight -------------------------------------------------------------------------------------
if [ -n "${AVC_PREFLIGHT_CMD:-}" ]; then
  bash -c "$AVC_PREFLIGHT_CMD" || fail "Preflight failed; the running API was NOT stopped."
else
  (cd "$ROOT/backend" && "$VENV/bin/python" -m app.config && "$VENV/bin/python" -c 'import app.main') \
    || fail "Preflight failed (configuration or import error); the running API was NOT stopped."
fi

# 2. identify the running API ------------------------------------------------------------------------
OLD=$(listener_pid "$API_PORT")
if [ -n "$OLD" ]; then
  case "$(cmdline "$OLD")" in
    *"$API_MATCH"*) ;;
    *) fail "Port $API_PORT is held by PID $OLD, which is not this project's API: $(cmdline "$OLD" | cut -c1-120). Not touching it." ;;
  esac
  [ -f "$PIDFILE" ] && [ "$(cat "$PIDFILE")" != "$OLD" ] && echo "note: $PIDFILE said $(cat "$PIDFILE"); the API actually listening is PID $OLD"
else
  # Not listening. A recorded PID that is still our API (hung/starting) is stopped too; anything else is ignored.
  if [ -f "$PIDFILE" ] && is_running "$(cat "$PIDFILE")"; then
    case "$(cmdline "$(cat "$PIDFILE")")" in *"$API_MATCH"*) OLD=$(cat "$PIDFILE") ;; esac
  fi
fi
if [ -n "$OLD" ]; then echo "API: running as PID $OLD"; else echo "API: not running"; fi

# 3. storefronts ---------------------------------------------------------------------------------
STORES_BEFORE=$(store_pids)
echo "Storefront PIDs (port:pid): $STORES_BEFORE"

# 4. keep the old log --------------------------------------------------------------------------------
if [ -s "$LOG" ]; then
  BACKUP="$LOG.$(date +%Y%m%d-%H%M%S)"
  cp -p "$LOG" "$BACKUP"
  echo "Log kept: $BACKUP"
fi

# 5. stop the old API -----------------------------------------------------------------------------
if [ -n "$OLD" ]; then
  kill -TERM "$OLD" 2>/dev/null || true
  waited=0
  while is_running "$OLD"; do
    if [ "$waited" -ge $((STOP_TIMEOUT * 2)) ]; then
      fail "Old API (PID $OLD) did not exit within ${STOP_TIMEOUT}s; no second copy was started. It may still be serving. Nothing else was touched."
    fi
    sleep 0.5; waited=$((waited + 1))
  done
  echo "Old API (PID $OLD) exited"
fi
waited=0
while [ -n "$(listener_pid "$API_PORT")" ]; do
  [ "$waited" -ge 20 ] && fail "Port $API_PORT is still in use by PID $(listener_pid "$API_PORT"); the new API was not started."
  sleep 0.5; waited=$((waited + 1))
done

# 6. start the new API and verify it --------------------------------------------------------------------
(cd "$API_DIR" || exit 1; nohup "${API_CMD[@]}" </dev/null >"$LOG" 2>&1 & echo $! >"$PIDFILE")
NEW=$(cat "$PIDFILE")
echo "New API started as PID $NEW; waiting for health…"
BODY=""
waited=0
while :; do
  if ! is_running "$NEW"; then
    echo "!! The new API (PID $NEW) exited during startup. Last log lines ($LOG):" >&2
    tail -n 20 "$LOG" >&2 || true
    rm -f "$PIDFILE"
    fail "API restart failed. PostgreSQL and the storefronts were not touched. Fix the error, then run this script again."
  fi
  if [ "$(listener_pid "$API_PORT")" = "$NEW" ]; then
    BODY=$(curl -s -m 3 "$HEALTH_URL" || true)
    [ -n "$BODY" ] && break
  fi
  [ "$waited" -ge $((HEALTH_TIMEOUT * 2)) ] && fail "New API (PID $NEW) did not answer $HEALTH_URL within ${HEALTH_TIMEOUT}s. It is still running; see $LOG."
  sleep 0.5; waited=$((waited + 1))
done
echo "Health: $BODY"

# 7. storefronts must be exactly as before -------------------------------------------------------------
STORES_AFTER=$(store_pids)
if [ "$STORES_AFTER" != "$STORES_BEFORE" ]; then
  fail "Storefront PIDs changed ($STORES_BEFORE -> $STORES_AFTER). This script never signals them; investigate."
fi
echo "Storefront PIDs unchanged: $STORES_AFTER"
echo "API restarted: ${OLD:-none} -> $NEW"

OK_RE='"status"[[:space:]]*:[[:space:]]*"ok"'
if [[ "$BODY" =~ $OK_RE ]]; then exit 0; fi
echo "!! The API is running but reports a non-ok status (see Health above)." >&2
exit 3
