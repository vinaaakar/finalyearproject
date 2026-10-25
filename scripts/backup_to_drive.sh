#!/usr/bin/env bash
# Create a backup of project source + docs + database dumps and place it in Google Drive
# (My Drive/AI-Voice-Commerce/project-backups). Run manually; nothing calls this automatically.
#
# Excluded on purpose: .env (secrets), node_modules, .venv, build output, runtime logs.
# The databases contain only synthetic demo data. If you ever load real customer data,
# do NOT use this script without encryption and a data-handling review.
source "$(dirname "$0")/_common.sh"
cd "$ROOT"

DRIVE_ROOT=$(ls -d "$HOME"/Library/CloudStorage/GoogleDrive-*/"My Drive" 2>/dev/null | head -1)
[ -n "$DRIVE_ROOT" ] || { echo "!! Google Drive for desktop folder not found." >&2; exit 1; }
DEST="$DRIVE_ROOT/AI-Voice-Commerce/project-backups"
STAMP=$(date +%Y%m%d-%H%M%S)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

echo "==> Dumping store databases (synthetic data)"
mkdir -p "$WORK/db"
for db in store_a store_b; do
  docker exec avc_postgres pg_dump -U postgres --no-owner "$db" > "$WORK/db/$db.sql"
done

echo "==> Archiving source and docs (no .env, no dependencies)"
tar -czf "$WORK/ai-voice-commerce-$STAMP.tar.gz" \
  --exclude='./.env' --exclude='*/node_modules' --exclude='./backend/.venv' --exclude='*/dist' \
  --exclude='./.run' --exclude='*/__pycache__' --exclude='*/.pytest_cache' \
  -C "$ROOT" . -C "$WORK" db

if tar -tzf "$WORK/ai-voice-commerce-$STAMP.tar.gz" | grep -qE '(^|/)\.env$'; then
  echo "!! .env found in archive; aborting" >&2; exit 1
fi

shasum -a 256 "$WORK/ai-voice-commerce-$STAMP.tar.gz" | awk '{print $1}' > "$WORK/ai-voice-commerce-$STAMP.tar.gz.sha256"
mkdir -p "$DEST"
cp "$WORK/ai-voice-commerce-$STAMP.tar.gz" "$WORK/ai-voice-commerce-$STAMP.tar.gz.sha256" "$DEST/"
echo "==> Copied to: $DEST"
echo "    SHA-256: $(cat "$WORK/ai-voice-commerce-$STAMP.tar.gz.sha256")"
echo "    Upload happens in the background. Confirm it on drive.google.com (same size) before relying on it."
