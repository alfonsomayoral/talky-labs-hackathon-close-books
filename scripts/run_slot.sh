#!/bin/zsh
# Run a heavy command in one of two machine-wide slots (24 GB of RAM: two holdout runs fit, three do not).
# Usage: scripts/run_slot.sh <command...>
# Waits for a free slot and for >= 8 GB of free memory, runs the command, releases the slot. Stale slots
# (owner process gone) are reclaimed. Every session uses this instead of its own check.
set -u
SLOTS=/tmp/closebooks-slots
MIN_FREE_GB=${MIN_FREE_GB:-8}
mkdir -p "$SLOTS"

free_gb() {
  vm_stat | awk '/Pages free|Pages inactive|Pages speculative/{s+=$3} END{printf "%d", s*16384/1073741824}'
}

acquire() {
  while true; do
    for i in 1 2; do
      local d="$SLOTS/$i"
      if mkdir "$d" 2>/dev/null; then
        echo $$ > "$d/pid"; echo "$i"; return
      fi
      local owner; owner=$(cat "$d/pid" 2>/dev/null || echo 0)
      if [ "$owner" != "0" ] && ! kill -0 "$owner" 2>/dev/null; then
        rm -rf "$d"  # stale: owner died
      fi
    done
    sleep 15
  done
}

slot=$(acquire)
trap 'rm -rf "$SLOTS/$slot"' EXIT INT TERM
while [ "$(free_gb)" -lt "$MIN_FREE_GB" ]; do sleep 30; done
echo "[run_slot] slot $slot, $(free_gb) GB free, $(date +%H:%M:%S): $*" >&2
"$@"
