#!/usr/bin/env bash
# Holt die Quelldaten auf EXAKT die Staende, gegen die die Items verifiziert wurden. Idempotent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
RAW="$ROOT/data/raw"; mkdir -p "$RAW"
fetch() { # name url sha
  local dir="$RAW/$1"
  if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD)" = "$3" ]; then echo "[=] $1 bereits auf $3"; return; fi
  rm -rf "$dir"; mkdir -p "$dir"; git -C "$dir" init -q; git -C "$dir" remote add origin "$2"
  git -C "$dir" fetch -q --depth 1 origin "$3"; git -C "$dir" checkout -q FETCH_HEAD
  [ "$(git -C "$dir" rev-parse HEAD)" = "$3" ] || { echo "[X] $1: falscher Commit"; exit 1; }
  echo "[+] $1 @ $3"
}
fetch hadith-json https://github.com/AhmedBaset/hadith-json.git 70b83d6d21995bb32f8d7271cd75501be5a922a7
fetch quran-json  https://github.com/risan/quran-json.git       6523a9ad3b73bb7e8cb3a9cdf0ea774b8bab3123
