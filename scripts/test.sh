#!/usr/bin/env bash
# Service-script safety tests + backend tests (against the *_test databases) + production build of both storefronts.
# A healthy Postgres container is never touched (see ensure_postgres in _common.sh).
source "$(dirname "$0")/_common.sh"
cd "$ROOT"
echo "==> Service-script safety tests (mocked Docker; no real service is touched)"
"$VENV/bin/python" -m pytest -q -p no:cacheprovider scripts/tests
ensure_postgres || { echo "!! Postgres is not available; backend tests not run." >&2; exit 1; }
echo "==> Backend tests"
(cd backend && "$VENV/bin/python" -m pytest -q -W ignore::DeprecationWarning "$@")
echo "==> Frontend build check"
(cd frontend && npm run build --silent >/dev/null && echo "store-a and store-b built OK")
