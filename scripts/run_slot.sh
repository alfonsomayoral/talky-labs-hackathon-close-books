#!/bin/zsh
# Run a heavy command in one of two machine-wide slots (24 GB of RAM: two holdout runs fit, three do not).
# Usage: scripts/run_slot.sh <command...>
# Takes a ticket (FIFO), waits for a free slot and for >= 8 GB of free memory, runs the command, releases the slot.
# Stale slots and tickets (owner process gone) are reclaimed. Every session uses this instead of its own check.
set -u
SLOTS=/tmp/closebooks-slots
TICKETS=$SLOTS/tickets
MIN_FREE_GB=${MIN_FREE_GB:-8}
mkdir -p "$SLOTS" "$TICKETS"

free_gb() {
  vm_stat | awk '/Pages free|Pages inactive|Pages speculative/{s+=$3} END{printf "%d", s*16384/1073741824}'
}

alive() { kill -0 "$1" 2>/dev/null; }

ticket="$TICKETS/$(date +%s%N)-$$"
echo $$ > "$ticket"

my_turn() {
  # Oldest live ticket wins; tickets of dead processes are removed.
  for t in "$TICKETS"/*(N); do
    local owner; owner=$(cat "$t" 2>/dev/null || echo 0)
    if [ "$owner" = "0" ] || ! alive "$owner"; then rm -f "$t"; continue; fi
    [ "$t" = "$ticket" ] && return 0
    return 1
  done
  return 0
}

acquire() {
  while true; do
    if my_turn; then
      for i in 1 2; do
        local d="$SLOTS/$i"
        if mkdir "$d" 2>/dev/null; then
          echo $$ > "$d/pid"; echo "$i"; return
        fi
        local owner; owner=$(cat "$d/pid" 2>/dev/null || echo 0)
        if [ "$owner" != "0" ] && ! alive "$owner"; then rm -rf "$d"; fi
      done
    fi
    sleep 10
  done
}

slot=$(acquire)
rm -f "$ticket"
trap 'rm -rf "$SLOTS/$slot"' EXIT INT TERM
while [ "$(free_gb)" -lt "$MIN_FREE_GB" ]; do sleep 30; done
echo "[run_slot] slot $slot, $(free_gb) GB free, $(date +%H:%M:%S): $*" >&2
"$@"
