#!/usr/bin/env bash
# Put verified local whisper.cpp models inside the project (models/whisper/, git-ignored), so speech recognition does not
# depend on files owned by another application. Copies only — never downloads. Each file must match the SHA-1 published
# by whisper.cpp (models/download-ggml-model.sh); anything else is refused and nothing is written.
#
#   scripts/setup_speech_models.sh --multilingual /path/to/ggml-base.bin [--english /path/to/ggml-base.en.bin]
#
# Afterwards set (or leave unset to use these defaults) in .env:
#   WHISPER_MODEL_PATH=<project>/models/whisper/ggml-base.bin
#   WHISPER_EN_MODEL_PATH=<project>/models/whisper/ggml-base.en.bin
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$ROOT/models/whisper"
declare -a PAIRS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --multilingual) PAIRS+=("ggml-base.bin|465707469ff3a37a2b9b8d8f89f2f99de7299dac|$2"); shift 2 ;;
    --english)      PAIRS+=("ggml-base.en.bin|137c40403d78fd54d454da0f9bd998f78703390c|$2"); shift 2 ;;
    *) echo "usage: $0 --multilingual <ggml-base.bin> [--english <ggml-base.en.bin>]" >&2; exit 2 ;;
  esac
done
[ ${#PAIRS[@]} -gt 0 ] || { echo "nothing to do (see --help in the header)" >&2; exit 2; }
for pair in "${PAIRS[@]}"; do
  IFS='|' read -r name sha src <<<"$pair"
  [ -f "$src" ] || { echo "!! $src not found" >&2; exit 1; }
  got=$(shasum -a 1 "$src" | cut -d' ' -f1)
  [ "$got" = "$sha" ] || { echo "!! $src: SHA-1 $got is not the official $name ($sha); refusing" >&2; exit 1; }
done
need=0; for pair in "${PAIRS[@]}"; do IFS='|' read -r _ _ src <<<"$pair"; need=$((need + $(stat -f %z "$src"))); done
free=$(df -k "$ROOT" | awk 'NR==2 {print $4 * 1024}')
[ "$free" -gt $((need * 4)) ] || { echo "!! not enough free disk space ($free bytes free, need $need)" >&2; exit 1; }
mkdir -p "$DEST"
for pair in "${PAIRS[@]}"; do
  IFS='|' read -r name sha src <<<"$pair"
  if [ -f "$DEST/$name" ] && [ "$(shasum -a 1 "$DEST/$name" | cut -d' ' -f1)" = "$sha" ]; then
    echo "==> $name already present and verified"; continue
  fi
  cp "$src" "$DEST/$name.partial"
  [ "$(shasum -a 1 "$DEST/$name.partial" | cut -d' ' -f1)" = "$sha" ] || { rm -f "$DEST/$name.partial"; echo "!! copy of $name corrupted" >&2; exit 1; }
  mv "$DEST/$name.partial" "$DEST/$name"
  echo "==> $name copied and verified ($sha)"
done
