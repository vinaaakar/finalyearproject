#!/usr/bin/env bash
# One-time (idempotent) local setup. Safe to re-run; never deletes data.
source "$(dirname "$0")/_common.sh"
cd "$ROOT"

echo "==> Checking free disk space"
FREE=$(free_mb); echo "    ${FREE} MB free (setup needs roughly 400 MB)"
if [ "$FREE" -lt 600 ]; then echo "!! Less than 600 MB free; aborting before installing anything." >&2; exit 1; fi

PY=$(find_python) || { echo "!! No working Python >= 3.11 found. Set PYTHON=/path/to/python3." >&2; exit 1; }
echo "==> Using Python: $PY ($("$PY" -V))"

if [ ! -f .env ]; then
  echo "==> Creating .env with freshly generated local secrets"
  gen() { "$PY" -c 'import secrets; print(secrets.token_urlsafe(32))'; }
  SECRET=$("$PY" -c 'import secrets; print(secrets.token_urlsafe(48))'); PGPW=$(gen); APW=$(gen); BPW=$(gen)
  sed -e "s|^APP_SECRET_KEY=.*|APP_SECRET_KEY=$SECRET|" \
      -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$PGPW|" \
      -e "s|^STORE_A_DB_PASSWORD=.*|STORE_A_DB_PASSWORD=$APW|" \
      -e "s|^STORE_B_DB_PASSWORD=.*|STORE_B_DB_PASSWORD=$BPW|" \
      -e "s|store_a_app:change-me-a@|store_a_app:$APW@|" \
      -e "s|store_b_app:change-me-b@|store_b_app:$BPW@|" \
      .env.example > .env
  chmod 600 .env
else
  echo "==> .env exists; leaving it unchanged"
fi

echo "==> Starting project Postgres container (avc_postgres on 127.0.0.1:5433)"
docker compose up -d postgres
for i in $(seq 1 40); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' avc_postgres 2>/dev/null)" = "healthy" ] && break
  sleep 1
done
[ "$(docker inspect -f '{{.State.Health.Status}}' avc_postgres)" = "healthy" ] || { echo "!! Postgres did not become healthy" >&2; exit 1; }

echo "==> Python virtual environment (backend/.venv)"
[ -x "$VENV/bin/python" ] || "$PY" -m venv "$VENV"
"$VENV/bin/pip" install -q --disable-pip-version-check -r backend/requirements-dev.txt

echo "==> Validating configuration"
(cd backend && "$VENV/bin/python" -m app.config)

echo "==> Migrating and seeding store databases (synthetic demo data)"
(cd backend && "$VENV/bin/python" -m app.migrate && "$VENV/bin/python" -m app.seed)

echo "==> Frontend dependencies (npm workspaces, shared node_modules)"
(cd frontend && npm install --no-audit --no-fund --loglevel=error)

echo "==> Done. Free space now: $(free_mb) MB. Start everything with: scripts/start.sh"
