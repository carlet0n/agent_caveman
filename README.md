# Agent Caveman

Token-efficient multi-agent workflows for Claude Code.

Agent Caveman reduces token spend on the orchestrator-to-subagent channel that multi-agent workflows consume invisibly.

## What it does

Multi-agent workflows in Claude Code (subagents spawned via `Agent`/`Task`) incur three token costs that compound quickly:

1. **Subagent responses** — narrative reports where the orchestrator needs only the facts.
2. **WebFetch responses** — frequently dominant in total token spend; disciplined extraction prompts reduce them by roughly an order of magnitude.
3. **Tool schemas** — the full tool list delivered to every subagent, including tools it will never invoke.

Agent Caveman addresses each at the source: subagent definitions with minimal tool whitelists, a strict output contract in each subagent's system prompt, and a skill that routes the lead agent to the appropriate specialist and enforces tight WebFetch prompts. A `PreToolUse` hook rewrites loose `WebFetch` and `Agent` prompts before execution, appending extraction discipline when the prompt lacks it. A `PostToolUse` hook trims bloated GitHub MCP responses. Measurement hooks record per-call cost to local JSONL so the effect is auditable.

Built-in tool output is not rewritten: Claude Code's hook contract permits mutation only of MCP responses (`updatedMCPToolOutput`). Savings on built-in tools come from generating less in the first place.

## Install

```bash
claude plugin marketplace add carlet0n/agent_caveman
claude plugin install agent-caveman@agent-caveman
```

No configuration. The `grunt-*` subagents become available to the orchestrator, hooks register automatically, and prompt rewriting is on by default (set `GRUNT_REWRITE=off` to disable).

### Local development

```bash
git clone https://github.com/carlet0n/agent_caveman.git
cd agent_caveman
claude --plugin-dir ./agent-caveman
```

## Usage

The system operates on four automatic layers.

**1. Specialized subagents.** Three focused alternatives to `general-purpose`:

| Agent             | Role                      | Tools                                        |
|-------------------|---------------------------|----------------------------------------------|
| `grunt-researcher`| Web + docs research       | `WebFetch`, `WebSearch`, `Read`, `Grep`, `Glob` |
| `grunt-explorer`  | Read-only codebase survey | `Read`, `Grep`, `Glob`, `Bash` (inspection only) |
| `grunt-coder`     | Execute scoped code edits | `Read`, `Edit`, `Write`, `Bash`, `Grep`, `Glob` |

Each subagent declares a `RESULT / FINDINGS / FILES / NEXT` output contract in its system prompt. The tool whitelists reduce the schema payload: Claude Code does not ship descriptions for tools the subagent cannot invoke.

**2. Orchestrator and subagent skills.**

- `grunt-orchestrator` — activates when the lead agent spawns a subagent or calls WebFetch. Supplies a task-to-subagent routing table and extraction-prompt patterns.
- `grunt-terse` — invoked by a subagent before returning its final report to enforce the `RESULT / FINDINGS / NEXT` format.

**3. Prompt rewriter.** A `PreToolUse` hook appends an extraction contract to `WebFetch` and `Agent`/`Task` prompts that lack one. Each rewrite is recorded to `.grunt/rewrites.jsonl` with the full before/after.

**4. Measurement.** A `PreToolUse`/`PostToolUse` pair writes one JSONL record per tool call to `.grunt/metrics.jsonl` within the active project. In-session report:

```
/agent-caveman:grunt-stats
```

Or run the underlying script directly:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/hooks/grunt_report.py"
```

Sample output:

```
sessions rows: 194  total in≈14571 tok  out≈236823 tok

tool                   calls    in_tok   out_tok   avg_out
WebFetch                  28      1009    200843      7172
Edit                      11      3317     20071      1824
Agent                      9      2428      2285       253
Bash                      17      1449      1805       106

subagent return cost (tok per call):
  general-purpose      n=4 avg=432 max=679
  claude-code-guide    n=4 avg=308 max=374

noisy Bash (>1000 tok out):
    2341 tok  find . -name "*.py"
full-file Reads (>2000 tok, no offset/limit):
    4621 tok  /path/to/big_file.txt
repeated Reads (≥3× same file):
  n=  3  /path/to/README.md
oversized subagent returns (>500 tok):
     679 tok  general-purpose        Build grunt-orchestrator skill

prompt rewrites applied: 2
  WebFetch             n=1
  Agent                n=1
```

Filter by session with `--session <id>`. The report leads with **authoritative usage** pulled from Claude Code's own session transcript (`~/.claude/projects/<cwd>/<session>.jsonl`) — real `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`, and `output_tokens` as returned by the API. Pass `--no-transcript` to skip it. The per-tool table below that row is hook-observed `len(s)//4` estimates, useful for comparing tool-by-tool trends but not billing reconciliation. For more accurate per-call numbers, set `GRUNT_TOKENIZER=tiktoken` (needs `pip install tiktoken`) or `GRUNT_TOKENIZER=anthropic` (needs `pip install anthropic` and a configured API key).

### Benchmarking savings

A reproducible A/B harness lives under `agent-caveman/bench/`. Each bench runs the same fixed task twice — once with plugin effects disabled (`GRUNT_REWRITE=off GRUNT_MCP_COMPRESS=off`), once with defaults — into isolated project dirs. `compare.py` reads each run's Claude Code session transcript and appends one row per run to `bench/history.jsonl`; `median.py` aggregates by task and reports median Δ with IQR.

```bash
./agent-caveman/bench/run_reps.sh agent-caveman/bench/tasks/github_mcp.md 5
python3 agent-caveman/bench/median.py
```

Current medians (Opus 4.6, 2026-04). IQR is the interquartile spread of per-rep Δ% — when `|median| < IQR`, treat the median as noise. Every row also reports `rw` (rewrites fired in treatment) and `mcp_saved_tok` (chars/4 from the MCP compressor); a row with both zero means **no plugin mechanism fired**, and any delta is model non-determinism.

| Task               | N  | Δ input (median, IQR) | Δ output (median, IQR) | rw_avg | mcp_saved_tok | What fired |
|--------------------|----|------------------------|-------------------------|--------|---------------|------------|
| `github_mcp`       | 10 | **−4.4%**, 6.2pp       | +0.3%, 2.8pp            | 0      | ~1,800        | MCP compressor (~3.5k tok saved per MCP call post-fix, ~47% per response) |
| `fan_out_ab`       | 5  | +2.0%, 0.3pp           | −0.2%, 6.4pp            | 5.0    | 0             | Paired-prompt whitelist A/B (baseline→`general-purpose`, treatment→`grunt-explorer`) + rewriter × 5 |
| `fan_out`          | 5  | +0.4%, 5.9pp           | +3.1%, 4.7pp            | 5.0    | 0             | Single-prompt (both pick `grunt-explorer`) → only rewriter cost |
| `webfetch_summary` | 6  | +7.4%, 8.0pp           | +2.4%, 11.7pp           | 9.3    | 0             | WebFetch rewriter ×9 per rep |
| `multi_agent`      | 5  | −0.0%, 0.6pp           | −1.6%, 49.3pp           | 1.0    | 0             | One subagent spawn + 1 rewrite |
| `_noop_control`    | 5  | −29.0%, 33.6pp         | −42.9%, 33.4pp          | **0**  | **0**         | Nothing — noise floor only |

Honest read:

- **`github_mcp` is the one confirmed win.** The compressor demonstrably strips ~47% of each GitHub MCP response, logged byte-for-byte in `.grunt/mcp_compress.jsonl`. IQR 6.2pp overlaps zero but a single MCP-heavy session can save tens of thousands of tokens.
- **The prompt rewriter currently costs more than it saves** on every workload we've tested. Each `WebFetch|Agent|Task` rewrite appends an extraction contract to the input; for tasks whose output was already going to be terse, the added input isn't repaid by output shrinkage.
- **The subagent whitelist has not demonstrated net savings yet.** `fan_out_ab` (the clean A/B: `general-purpose` vs `grunt-explorer` with everything else identical) shows +2.0% input with tight IQR. Possible explanations: (a) schema-cache behavior means the raw byte delta doesn't translate to billed tokens, (b) `grunt-explorer`'s custom system prompt offsets the tool-list savings, or (c) five 1-turn subagent spawns don't amortize enough. A 20-rep `deep_explore` task (one subagent, long internal loop) is running to probe this.
- **`_noop_control` demonstrates the noise floor.** It invokes only Read/Grep/Glob, which neither hook touches, so baseline and treatment run identical code paths. Any delta there — including the −29% — is pure sampling variation; the 33.6pp IQR makes that obvious. Use it to sanity-check other medians: if your effect is smaller than the noise floor IQR, it isn't an effect.

`bench/schema_size.py` prints the static tool-schema ceiling per subagent type. That's an upper bound, not a measured saving.

Where savings should show up in principle (when the `deep_explore` bench completes, we'll know whether they do):

- GitHub MCP–heavy sessions (confirmed)
- Long single-subagent explorations with many internal turns (pending)
- Workflows that spawn many subagents each doing multiple turns (pending)

Where the plugin currently has no path to help:

- One-shot Q&A with no subagents, no MCP, no WebFetch
- Short WebFetch tasks whose answers were already brief

See `agent-caveman/bench/README.md` for methodology and caveats (model is non-deterministic; run ≥5 reps and compare medians).

## How it works

### Subagents

`agent-caveman/agents/*.md` defines each subagent with a `tools:` frontmatter whitelist enforced by Claude Code. The subagent's system context carries schemas only for tools it can invoke.

Each subagent's system prompt enforces a compact report format:

```
RESULT: done
FINDINGS:
- JWT validation: `src/auth/middleware.ts:14` uses `jsonwebtoken`
- expiry + sig checked at `:22-31`
NEXT: none
```

### Hooks

Two hooks wired via the plugin's `hooks/hooks.json`:

- `grunt_log.py` (`PreToolUse` + `PostToolUse`, all tools) — records `{tool, input_tokens, output_tokens, metadata}` per call to `.grunt/metrics.jsonl`
- `grunt_rewrite.py` (`PreToolUse`, `WebFetch|Agent|Task`) — mutates `tool_input.prompt` via `updatedInput` when the prompt lacks discipline markers. Appends a terse-extraction contract to loose `WebFetch` prompts and a 200-word cap to `Agent`/`Task` prompts missing one. Every rewrite logged to `.grunt/rewrites.jsonl` with the full before/after. Disable per-session with `GRUNT_REWRITE=off`.
- `grunt_mcp_github.py` (`PostToolUse`, `mcp__github__.*`) — trims GitHub MCP tool responses via `updatedMCPToolOutput`. Drops `*_url` fields, `node_id`, `avatar_url`, `reactions`, and other rarely-read metadata; compacts `user` objects to `{login}` and `labels` to name arrays. Typical reduction is 60–75% on list payloads. Logged to `.grunt/mcp_compress.jsonl`. Disable with `GRUNT_MCP_COMPRESS=off`. Only activates if the GitHub MCP server is installed.

Pure Python 3 standard library. No dependencies, no network calls. Everything stays local to your project's `.grunt/` directory.

### Non-goals

- **Built-in tool output mutation.** Claude Code's hook contract permits post-execution mutation only for MCP tools (`updatedMCPToolOutput`); `grunt_mcp_github.py` uses this path. Built-in tool output — Bash, Read, Edit, WebFetch, Agent — is immutable to hooks, so reductions there come from input-side rewrites and subagent output contracts.
- **MCP wrapping of built-in tools.** Would bypass Claude Code's permission enforcement (e.g. the "Read before Edit" constraint) for modest schema savings.
- **Parameter renaming.** Shortening argument names (`file_path` → `p`) saves under 2% of tokens and measurably degrades tool-call accuracy.
- **LLM-based rewriting.** All reductions are deterministic and inspectable.
- **Cross-session learning.** Metrics are local, per-project JSONL.

## Repository layout

```
.
├── .claude-plugin/
│   └── marketplace.json        # marketplace manifest
├── agent-caveman/              # the plugin itself
│   ├── .claude-plugin/
│   │   └── plugin.json         # plugin manifest
│   ├── hooks/
│   │   ├── hooks.json          # hook registrations
│   │   ├── grunt_log.py        # PreToolUse/PostToolUse token logger
│   │   ├── grunt_rewrite.py    # PreToolUse prompt discipline rewriter
│   │   ├── grunt_mcp_github.py # PostToolUse GitHub MCP response trimmer
│   │   └── grunt_report.py     # summary CLI
│   ├── agents/
│   │   ├── grunt-researcher.md
│   │   ├── grunt-explorer.md
│   │   └── grunt-coder.md
│   ├── skills/
│   │   ├── grunt-orchestrator/SKILL.md  # subagent routing + WebFetch prompt discipline
│   │   └── grunt-terse/SKILL.md         # compact output format for subagent returns
│   └── commands/
│       └── grunt-stats.md      # /grunt-stats slash command
└── README.md
```

## Status

| Component | State |
|-----------|-------|
| Token measurement hooks + `/grunt-stats` report | Shipped |
| Three specialized subagents (`grunt-researcher`, `grunt-explorer`, `grunt-coder`) | Shipped |
| `grunt-orchestrator` skill (subagent routing + WebFetch prompt discipline) | Shipped |
| `grunt-terse` skill (compact output contract) | Shipped |
| PreToolUse prompt rewriter for WebFetch/Agent/Task | Shipped |
| `/grunt-stats` diagnostics: noisy Bash, full-file Reads, repeated Reads, oversized subagents | Shipped |
| GitHub MCP response compressor | Shipped |

## License

MIT.

## Credits

Inspired by [caveman](https://github.com/JuliusBrussee/caveman) by Julius Brussee, which compresses human-facing Claude output. Agent Caveman applies the same principle to the agent-to-agent channel.
