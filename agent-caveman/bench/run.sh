#!/usr/bin/env bash
# Run a fixed bench task twice — baseline (plugin effects off) vs treatment
# (plugin effects on) — and write each run's transcript into its own isolated
# CLAUDE_PROJECT_DIR so the results can be diffed.
#
# Usage: bench/run.sh <task-file> [label]
#
# Example:
#   bench/run.sh bench/tasks/webfetch_summary.md webfetch
#
# The script creates two throw-away project dirs under bench/runs/<label>/{baseline,treatment}
# and prints their paths. Feed both into bench/compare.py.

set -euo pipefail

TASK="${1:-}"
LABEL="${2:-$(basename "${TASK%.*}")}"
TREAT_TASK="${TREATMENT_TASK:-$TASK}"

if [ -z "$TASK" ] || [ ! -f "$TASK" ]; then
  echo "usage: $0 <task-file> [label]" >&2
  echo "  set TREATMENT_TASK=<file> to use a different prompt for the treatment run" >&2
  exit 2
fi
if [ ! -f "$TREAT_TASK" ]; then
  echo "TREATMENT_TASK file not found: $TREAT_TASK" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/agent-caveman"
RUN_ROOT="$REPO_ROOT/agent-caveman/bench/runs/$LABEL-$(date +%Y%m%d-%H%M%S)"
BASE_DIR="$RUN_ROOT/baseline"
TREAT_DIR="$RUN_ROOT/treatment"
mkdir -p "$BASE_DIR" "$TREAT_DIR"

BASE_PROMPT="$(cat "$TASK")"
TREAT_PROMPT="$(cat "$TREAT_TASK")"

run_one() {
  local variant="$1" proj="$2" prompt="$3"
  shift 3
  echo "[$variant] project=$proj"
  (
    cd "$proj"
    CLAUDE_PROJECT_DIR="$proj" "$@" claude -p \
      --add-dir "$REPO_ROOT" \
      --plugin-dir "$PLUGIN_DIR" \
      --dangerously-skip-permissions \
      "$prompt" > "$proj/stdout.txt" 2> "$proj/stderr.txt" || true
  )
  echo "[$variant] done ($(wc -c <"$proj/stdout.txt") bytes stdout)"
}

run_one baseline  "$BASE_DIR"  "$BASE_PROMPT"  env GRUNT_REWRITE=off GRUNT_MCP_COMPRESS=off
run_one treatment "$TREAT_DIR" "$TREAT_PROMPT"

echo
python3 "$PLUGIN_DIR/bench/compare.py" \
  --baseline  "$BASE_DIR" \
  --treatment "$TREAT_DIR" \
  --label "$LABEL"
