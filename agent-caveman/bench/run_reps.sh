#!/usr/bin/env bash
# Run one task N times to collect medians.
#
# Usage: bench/run_reps.sh <task-file> [reps=5]
#
# Each rep calls bench/run.sh with a label of <task>-repN, so compare.py
# appends one history row per rep. Aggregate with bench/median.py.

set -euo pipefail

TASK="${1:-}"
REPS="${2:-5}"

if [ -z "$TASK" ] || [ ! -f "$TASK" ]; then
  echo "usage: $0 <task-file> [reps=5]" >&2
  exit 2
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
STEM="$(basename "${TASK%.*}")"

for i in $(seq 1 "$REPS"); do
  echo "=== $STEM rep $i/$REPS ==="
  "$DIR/run.sh" "$TASK" "$STEM-rep$i"
done

echo
echo "medians:"
python3 "$DIR/median.py" --label "$STEM"
