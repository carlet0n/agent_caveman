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

if [ -z "$TASK" ] || [ ! -f "$TASK" ]; then
  echo "usage: $0 <task-file> [label]" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/agent-caveman"
RUN_ROOT="$REPO_ROOT/agent-caveman/bench/runs/$LABEL-$(date +%Y%m%d-%H%M%S)"
BASE_DIR="$RUN_ROOT/baseline"
TREAT_DIR="$RUN_ROOT/treatment"
mkdir -p "$BASE_DIR" "$TREAT_DIR"

PROMPT="$(cat "$TASK")"

run_one() {
  local variant="$1" proj="$2"
  shift 2
  echo "[$variant] project=$proj"
  (
    cd "$proj"
    CLAUDE_PROJECT_DIR="$proj" "$@" claude -p \
      --add-dir "$REPO_ROOT" \
      --plugin-dir "$PLUGIN_DIR" \
      --dangerously-skip-permissions \
      "$PROMPT" > "$proj/stdout.txt" 2> "$proj/stderr.txt" || true
  )
  echo "[$variant] done ($(wc -c <"$proj/stdout.txt") bytes stdout)"
}

run_one baseline  "$BASE_DIR"  env GRUNT_REWRITE=off GRUNT_MCP_COMPRESS=off
run_one treatment "$TREAT_DIR"

echo
echo "compare with:"
echo "  python3 $PLUGIN_DIR/bench/compare.py \\"
echo "    --baseline  $BASE_DIR \\"
echo "    --treatment $TREAT_DIR"
