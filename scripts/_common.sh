# Shared helpers for project scripts. Sourced, not executed.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/backend/.venv"
RUN_DIR="$ROOT/.run"

# Pick a working Python >= 3.11 without touching global settings.
# (On this machine the first `python3` on PATH crashes, so we test each candidate.)
find_python() {
  for c in "${PYTHON:-}" /opt/homebrew/bin/python3 python3.14 python3.13 python3.12 python3.11 python3; do
    [ -z "$c" ] && continue
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' >/dev/null 2>&1; then
      command -v "$c"; return 0
    fi
  done
  return 1
}

free_mb() { df -m "$ROOT" | awk 'NR==2 {print $4}'; }

# PID listening on a local TCP port (empty if none).
listener_pid() { lsof -nP -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1 || true; }

# ---- PostgreSQL guard -------------------------------------------------------------------------
# Scripts must NEVER run a bare `docker compose up` against the database: Compose recreates a running
# container whenever it thinks the configuration changed (for example after a Docker/Compose upgrade).
# The data volume survives that, but the database restarts. All scripts go through ensure_postgres:
#   - running and healthy  -> left completely untouched (no docker command other than `inspect` runs)
#   - still starting        -> wait for it, read-only
#   - running but unhealthy -> reported, never touched
#   - stopped               -> `docker start` (the SAME container; never recreated), only with approval
#   - missing               -> `docker compose up -d --no-recreate postgres`, only with approval
# Approval: answer "y" at the prompt, or set AVC_APPROVE_DB_START=1 for a non-interactive run.
PG_CONTAINER="${AVC_PG_CONTAINER:-avc_postgres}"
PG_WAIT_SECONDS="${AVC_PG_WAIT_SECONDS:-60}"

# Prints "<status>:<health>" (e.g. running:healthy, exited:none), "missing" or "docker-down". Read-only.
pg_state() {
  docker info >/dev/null 2>&1 || { echo "docker-down"; return 0; }
  docker inspect -f '{{.State.Status}}:{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$PG_CONTAINER" 2>/dev/null \
    || echo "missing"
}

pg_wait_healthy() { # read-only polling
  local i state
  for ((i = 0; i < PG_WAIT_SECONDS; i++)); do
    state=$(pg_state)
    [ "$state" = "running:healthy" ] && return 0
    case "$state" in running:starting) ;; *) echo "!! Postgres is now '$state'." >&2; return 1 ;; esac
    sleep 1
  done
  echo "!! Postgres did not become healthy within ${PG_WAIT_SECONDS}s (state: $(pg_state))." >&2
  return 1
}

pg_approved() { # $1 = description of the action
  if [ "${AVC_APPROVE_DB_START:-}" = "1" ]; then return 0; fi
  if [ -t 0 ] && [ -t 1 ]; then
    local ans=""
    read -r -p "?? $1 Proceed? [y/N] " ans || ans=""
    case "$ans" in y | Y | yes | YES) return 0 ;; esac
    echo "Not approved; leaving Postgres as it is." >&2
    return 1
  fi
  echo "!! Approval needed: $1" >&2
  echo "   Re-run interactively and answer 'y', or set AVC_APPROVE_DB_START=1." >&2
  return 1
}

ensure_postgres() {
  local state
  state=$(pg_state)
  case "$state" in
    running:healthy)
      echo "Postgres: $PG_CONTAINER is running and healthy (left untouched)"
      return 0 ;;
    running:starting)
      echo "Postgres: $PG_CONTAINER is starting; waiting (read-only)…"
      pg_wait_healthy && echo "Postgres: healthy" ;;
    docker-down)
      echo "!! Docker is not running. Start Docker Desktop, then run this again." >&2
      return 1 ;;
    exited:* | created:*)
      echo "Postgres: container $PG_CONTAINER exists but is stopped ($state)."
      pg_approved "Start the existing container with 'docker start $PG_CONTAINER' (same container and data volume; nothing is recreated)." || return 1
      docker start "$PG_CONTAINER" >/dev/null
      pg_wait_healthy && echo "Postgres: started and healthy" ;;
    missing)
      echo "Postgres: container $PG_CONTAINER does not exist."
      pg_approved "Create it with 'docker compose up -d --no-recreate postgres' (reuses the existing data volume if there is one)." || return 1
      (cd "$ROOT" && docker compose up -d --no-recreate postgres >/dev/null)
      pg_wait_healthy && echo "Postgres: created and healthy" ;;
    *)
      # running:unhealthy, running:none, paused, restarting, removing, dead …
      echo "!! Postgres container $PG_CONTAINER is in state '$state'. Not touching it." >&2
      echo "   Inspect with: docker logs --tail 50 $PG_CONTAINER" >&2
      return 1 ;;
  esac
}
