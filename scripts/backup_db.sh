#!/usr/bin/env bash
# Local, verified backup of both store databases (custom-format pg_dump, SHA-256, row counts, MANIFEST.json)
# into backups/db-<timestamp>/ (git-ignored, owner-only). Never uploads anything; never starts, stops or
# recreates the Postgres container. Other commands: scripts/dbsafety.py verify|restore-check|precheck.
source "$(dirname "$0")/_common.sh"
exec "$VENV/bin/python" "$ROOT/scripts/dbsafety.py" backup "$@"
