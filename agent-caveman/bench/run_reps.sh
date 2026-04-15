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
  echo "  pair tasks by convention: <stem>.baseline.md + <stem>.treatment.md" >&2
  echo "  — point at the .baseline.md file; the treatment sibling is auto-detected" >&2
  exit 2
fi

DIR="$(cd "$(dirname "$0")" && pwd)"
STEM="$(basename "${TASK%.*}")"

# Paired task convention: if TASK ends in .baseline.md and a sibling
# .treatment.md exists, run them as a two-prompt A/B.
if [[ "$TASK" == *.baseline.md ]]; then
  TREAT_SIBLING="${TASK%.baseline.md}.treatment.md"
  if [ -f "$TREAT_SIBLING" ]; then
    export TREATMENT_TASK="$TREAT_SIBLING"
    STEM="$(basename "${STEM%.baseline}")"
    echo "paired run: baseline=$TASK treatment=$TREAT_SIBLING"
  fi
fi

for i in $(seq 1 "$REPS"); do
  echo "=== $STEM rep $i/$REPS ==="
  "$DIR/run.sh" "$TASK" "$STEM-rep$i"
done

echo
echo "medians:"
python3 "$DIR/median.py" --label "$STEM"
