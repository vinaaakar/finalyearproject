#!/usr/bin/env bash
# Encrypted offsite copy of a verified database backup (Phase J). Run after scripts/backup_db.sh, e.g. from a daily timer
# (deploy/backup-offsite.timer, deploy/com.avc.backup-offsite.plist).
#
#   scripts/backup_offsite.sh --from backups/db-<timestamp> --dest <offsite dir> --key-file <key file> [--keep 14]
#   scripts/backup_offsite.sh --verify <offsite dir>/db-<timestamp>.tar.enc --key-file <key file>   (integrity check)
#
# --dest      a directory that is synchronised offsite (an rclone/S3 mount, a NAS share, a cloud-drive folder…)
# --key-file  32+ random bytes kept OUTSIDE the project with mode 600 (generate once: openssl rand -base64 48 > key;
#             chmod 600 key) and stored separately from the backups (password manager / secrets vault). Without it the
#             copies cannot be restored.
# What it does: refuses unless the backup verifies against its MANIFEST (checksums), encrypts the whole backup folder
# (AES-256-CBC, key from PBKDF2 with 200 000 iterations), writes <name>.tar.enc, an HMAC-SHA256 of it keyed from the key
# file (<name>.tar.enc.hmac: detects ANY change and a wrong key before decrypting) and a plain SHA-256 (for transfer
# checks), then DECRYPTS the copy again and re-checks every file against the manifest before counting it as good. Old copies beyond --keep are
# removed only after the new one verified. The key is never printed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FROM="" DEST="" KEY="" KEEP=14 VERIFY=""
while [ $# -gt 0 ]; do
  case "$1" in
    --verify) VERIFY="$2"; shift 2 ;; --from) FROM="$2"; shift 2 ;; --dest) DEST="$2"; shift 2 ;; --key-file) KEY="$2"; shift 2 ;; --keep) KEEP="$2"; shift 2 ;;
    *) echo "usage: $0 --from backups/db-<ts> --dest <dir> --key-file <file> [--keep N]" >&2; exit 2 ;;
  esac
done
if [ -z "$KEY" ] || { [ -z "$VERIFY" ] && { [ -z "$FROM" ] || [ -z "$DEST" ]; }; }; then
  echo "usage: $0 --from backups/db-<ts> --dest <dir> --key-file <file> [--keep N] | --verify <file.tar.enc> --key-file <file>" >&2; exit 2
fi
[ -f "$KEY" ] || { echo "!! key file not found" >&2; exit 1; }
KEYABS="$(cd "$(dirname "$KEY")" && pwd)/$(basename "$KEY")"
case "$KEYABS" in "$ROOT"/*) echo "!! the key file must be outside the project directory" >&2; exit 1 ;; esac
perm=$(stat -f %Lp "$KEYABS" 2>/dev/null || stat -c %a "$KEYABS")
[ "$perm" = "600" ] || [ "$perm" = "400" ] || { echo "!! key file permissions are $perm; run chmod 600 on it" >&2; exit 1; }
[ "$(wc -c < "$KEYABS")" -ge 32 ] || { echo "!! key file is too short (need 32+ bytes)" >&2; exit 1; }
PYTHON="$ROOT/backend/.venv/bin/python"; [ -x "$PYTHON" ] || PYTHON="$(command -v python3)"

check_manifest() {   # $1 = folder containing MANIFEST.json and the dump files
  "$PYTHON" - "$1" <<'PY'
import hashlib, json, pathlib, sys
d = pathlib.Path(sys.argv[1]); m = json.loads((d / "MANIFEST.json").read_text())
for db, info in m["databases"].items():
    got = hashlib.sha256((d / info["file"]).read_bytes()).hexdigest()
    if got != info["sha256"]:
        sys.exit(f"!! {db}: checksum mismatch")
print(f"    manifest ok: {', '.join(sorted(m['databases']))}")
PY
}

hmac_of() {   # HMAC-SHA256 of file $1, keyed by SHA-256 of the key file (the key never appears in process arguments)
  "$PYTHON" - "$1" "$KEYABS" <<'PY'
import hashlib, hmac, sys
key = hashlib.sha256(open(sys.argv[2], "rb").read()).digest()
h = hmac.new(key, digestmod=hashlib.sha256)
with open(sys.argv[1], "rb") as f:
    for chunk in iter(lambda: f.read(1 << 20), b""):
        h.update(chunk)
print(h.hexdigest())
PY
}

verify_copy() {   # $1 = .tar.enc
  local file="$1" expected got work name
  [ -f "$file.hmac" ] || { echo "!! $file.hmac missing" >&2; return 1; }
  expected="$(cat "$file.hmac")"; got="$(hmac_of "$file")"
  [ "$expected" = "$got" ] || { echo "!! $(basename "$file"): HMAC mismatch - the file was changed or the key is wrong" >&2; return 1; }
  work="$(mktemp -d)"
  openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass "file:$KEYABS" -in "$file" | tar -C "$work" -xf -
  name="$(ls "$work")"
  if ! check_manifest "$work/$name"; then rm -rf "$work"; return 1; fi
  rm -rf "$work"
}

if [ -n "$VERIFY" ]; then
  echo "==> Verifying $(basename "$VERIFY")"
  verify_copy "$VERIFY"
  echo "==> OK: authentic, decrypts, every dump matches its manifest checksum"
  exit 0
fi

FROM="$(cd "$FROM" && pwd)"; NAME="$(basename "$FROM")"
[ -f "$FROM/MANIFEST.json" ] || { echo "!! $FROM has no MANIFEST.json" >&2; exit 1; }
mkdir -p "$DEST"
echo "==> Verifying $NAME against its manifest"
check_manifest "$FROM"
OUT="$DEST/$NAME.tar.enc"
[ -e "$OUT" ] && { echo "==> $OUT already exists; not overwriting"; exit 0; }
echo "==> Encrypting to $OUT"
tar -C "$(dirname "$FROM")" -cf - "$NAME" | openssl enc -aes-256-cbc -salt -pbkdf2 -iter 200000 -pass "file:$KEYABS" -out "$OUT.partial"
hmac_of "$OUT.partial" > "$OUT.partial.hmac"
echo "==> Verifying the encrypted copy (HMAC, decrypt, manifest)"
verify_copy "$OUT.partial"
mv "$OUT.partial" "$OUT"; mv "$OUT.partial.hmac" "$OUT.hmac"
( cd "$DEST" && shasum -a 256 "$(basename "$OUT")" > "$(basename "$OUT").sha256" )
echo "==> Stored $(basename "$OUT") ($(wc -c < "$OUT" | tr -d ' ') bytes)"
# Retention: only verified copies (with an .hmac) count; remove the oldest beyond --keep.
ls -1 "$DEST"/*.tar.enc 2>/dev/null | sort | head -n -"$KEEP" 2>/dev/null | while read -r old; do
  [ -f "$old.hmac" ] && rm -f "$old" "$old.hmac" "$old.sha256" && echo "    removed old copy $(basename "$old")"
done || true
