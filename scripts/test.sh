#!/usr/bin/env bash
# Backend tests (against the *_test databases) + production build of both storefronts.
source "$(dirname "$0")/_common.sh"
cd "$ROOT"
docker compose up -d postgres >/dev/null
for i in $(seq 1 30); do
  [ "$(docker inspect -f '{{.State.Health.Status}}' avc_postgres 2>/dev/null)" = "healthy" ] && break; sleep 1
done
echo "==> Backend tests"
(cd backend && "$VENV/bin/python" -m pytest -q -W ignore::DeprecationWarning "$@")
echo "==> Frontend build check"
(cd frontend && npm run build --silent >/dev/null && echo "store-a and store-b built OK")
