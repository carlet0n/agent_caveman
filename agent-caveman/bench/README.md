# Agent Caveman bench harness

Reproducible A/B for plugin savings. Each bench run executes the same task
twice — once with plugin effects disabled (baseline), once with them on
(treatment) — into isolated `CLAUDE_PROJECT_DIR`s. The two session
transcripts are then diffed.

## Run a single task

```bash
./bench/run.sh bench/tasks/webfetch_summary.md
```

That produces two project dirs under `bench/runs/<label>-<timestamp>/`
(`baseline/` and `treatment/`) and prints the compare command. Baseline sets
`GRUNT_REWRITE=off` and `GRUNT_MCP_COMPRESS=off`; treatment uses defaults.

Both runs use `claude -p --plugin-dir <repo>/agent-caveman
--dangerously-skip-permissions`.

`run.sh` auto-invokes `compare.py` at the end and appends one summary row
to `bench/history.jsonl` so results accumulate across runs.

## Compare

```bash
python3 bench/compare.py \
  --baseline  bench/runs/<label>/baseline \
  --treatment bench/runs/<label>/treatment
```

Appends to `bench/history.jsonl` by default. Pass `--history ''` to skip,
or `--history <path>` to redirect.

## History

```bash
python3 bench/history.py                # table of all past runs
python3 bench/history.py --label webfetch
python3 bench/history.py --tail 20
python3 bench/history.py --json         # raw JSONL
```

Output sections:

- **authoritative usage** — real `input_tokens` / `cache_*` / `output_tokens`
  pulled from `~/.claude/projects/<cwd>/<session>.jsonl`. This is the billable
  number.
- **hook-observed per-tool out_tok** — char/4 estimates from
  `.grunt/metrics.jsonl` grouped by tool. Useful for seeing *which* tool's
  response shrank.
- **plugin effects** — rewrite counts and MCP bytes saved per run.

## Tasks

| Task                              | Exercises                                                    |
|-----------------------------------|--------------------------------------------------------------|
| `tasks/webfetch_summary.md`       | WebFetch volume; prompt rewriter on loose fetch prompts.     |
| `tasks/repo_survey.md`            | Read/Glob/Grep load; subagent output contract.               |
| `tasks/multi_agent.md`            | Subagent tool-schema footprint; whitelist savings.           |

Add more by dropping a `.md` prompt into `bench/tasks/`.

## Caveats

- Token counts between two runs will never match exactly. Model is
  non-deterministic and tool paths vary. Run each task 3–5× and look at
  medians, not point comparisons.
- Treatment cannot disable subagent whitelists from env alone. To measure that
  slice, use a task prompt that names `grunt-explorer` in treatment and
  `general-purpose` in baseline.
- `claude -p` still consults your normal auth. No network-free mode.
