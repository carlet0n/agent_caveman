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

A reproducible A/B harness lives under `agent-caveman/bench/`. Each bench runs the same fixed task twice — once with plugin effects disabled (`GRUNT_REWRITE=off GRUNT_MCP_COMPRESS=off`), once with defaults — into isolated project dirs. `compare.py` reads each run's Claude Code session transcript and appends one row per run to `bench/history.jsonl`; `median.py` aggregates by task.

```bash
./agent-caveman/bench/run_reps.sh agent-caveman/bench/tasks/repo_survey.md 5
python3 agent-caveman/bench/median.py
```

Medians from 5 reps per task (Opus 4.6, 2026-04):

| Task              | Δ total_input | Δ output_tokens | Exercises                                |
|-------------------|---------------|------------------|------------------------------------------|
| `repo_survey`     | **−29.0%**    | **−42.9%**       | Subagent tool-whitelist + output contract |
| `github_mcp`      | **−6.2%**     | +0.4%            | GitHub MCP response compressor (~3.5k tok saved per MCP call, ~47% per response) |
| `multi_agent`     | −0.0%         | −8.3%            | Subagent schema footprint                |
| `fan_out`         | +0.3%         | +3.9%            | 5× subagent spawn; both variants use `grunt-explorer` so only rewriter cost is measured |
| `webfetch_summary`| +4.3%         | +1.6%            | WebFetch prompt rewriter                  |

`fan_out` and `webfetch_summary` turning slightly positive is the honest cost of the rewriter's extraction-contract append when the workload doesn't also harvest savings elsewhere. A proper A/B of the whitelist slice requires two prompts (baseline → `general-purpose`, treatment → `grunt-explorer`) — see `bench/README.md`.

Signal: savings scale with subagent turn count × tools-not-needed. Repo-survey workflows (enumerate, audit, delegate file reads) benefit most. Single-shot tasks with already-tight WebFetch prompts lose a small amount to the rewriter's extraction contract.

Workflows that benefit:

- Codebase surveys, audits, compliance sweeps
- Architecture/doc generation from source
- Bug triage that delegates to subagents repeatedly
- Refactor planning (explorer → coder handoff)
- PR review of large diffs

Workflows that don't:

- Short single-turn Q&A with no subagents
- Pure WebFetch tasks whose answers are already terse

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
