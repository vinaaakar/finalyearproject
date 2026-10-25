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
