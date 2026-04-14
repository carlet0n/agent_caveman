# Agent Caveman

Token-efficient multi-agent workflows for Claude Code.

Caveman makes humans talk to Claude in fewer tokens. Agent Caveman makes *Claude talk to Claude* in fewer tokens — the orchestrator-to-subagent channel that multi-agent workflows burn through invisibly.

## What it does

When you run multi-agent workflows in Claude Code (spawning subagents via the `Agent`/`Task` tool), three things quietly eat tokens:

1. **Subagent responses** — long narrative reports where the orchestrator only needed the facts
2. **Tool outputs** — verbose `ls -l`, pretty-printed JSON, ANSI colors, trailing whitespace
3. **Tool schemas** — the full tool list shipped to every subagent, even tools the subagent will never call

Agent Caveman attacks all three. It ships opinionated subagent definitions with minimal tool whitelists and terse output contracts, then uses hooks to measure and compress tool output before it ever reaches the model.

There's no terseness level to tune. Agent-to-agent channels have no human reader to please, so compression is always set to "as compact as possible while preserving technical substance." Code, commands, paths, file:line references, and error strings are never touched.

## Install

One line, no approval gate — Claude Code plugin marketplaces install from any public GitHub repo directly:

```bash
claude plugin marketplace add carlet0n/agent_caveman && claude plugin install agent-caveman@agent-caveman
```

That's it. No mode to enable, no level to pick, no configuration. Hooks register automatically and the `grunt-*` subagents become available to the orchestrator.

> Anthropic does not gate or review user marketplaces — any public GitHub repo works. (There is a separate opt-in curated marketplace Anthropic runs, which accepts submissions via `claude.ai/settings/plugins/submit`.)

### Local development install

To hack on the plugin, point Claude Code at a working copy:

```bash
git clone https://github.com/carlet0n/agent_caveman.git
cd agent-caveman
claude --plugin-dir ./agent-caveman
```

## Usage

Nothing to invoke. The system operates on three layers, all automatic:

**1. Specialized subagents.** When the orchestrator would normally spawn a `general-purpose` agent, it now has three tighter options:

| Agent             | Role                      | Tools                                        |
|-------------------|---------------------------|----------------------------------------------|
| `grunt-researcher`| Web + docs research       | `WebFetch`, `WebSearch`, `Read`, `Grep`, `Glob` |
| `grunt-explorer`  | Read-only codebase survey | `Read`, `Grep`, `Glob`, `Bash` (inspection only) |
| `grunt-coder`     | Execute scoped code edits | `Read`, `Edit`, `Write`, `Bash`, `Grep`, `Glob` |

Each ships a strict output contract in its system prompt (`RESULT / FINDINGS / FILES / NEXT` blocks), so returns are structured facts rather than prose.

**2. Tool-output compression.** A `PostToolUse` hook inspects every tool response, applies tool-specific rules (strip ANSI, collapse blank lines, drop `ls -l` metadata columns, trim agent-response preambles and closings), and logs before/after token counts.

**3. Measurement.** A `PreToolUse`/`PostToolUse` pair writes one JSONL record per tool call to `.grunt/metrics.jsonl` in whichever project you're working in. You can see what the system is saving at any time:

```bash
python3 "$CLAUDE_PLUGIN_ROOT/hooks/grunt_report.py"
```

Sample output:

```
sessions rows: 53  total in≈4873 tok  out≈6913 tok

tool                   calls    in_tok   out_tok   avg_out
Write                      4      2548      2604       651
Agent                      3       916      1051       350
Bash                      10       573       783        78

subagent return cost (tok per call):
  general-purpose      n=3 avg=350 max=387

compression potential: 155/3245 tok saved (4.8%)
  Agent                n=3    735/1051 (70.0%)
  Bash                 n=5    155/392  (39.5%)
```

Filter by session with `--session <id>`.

## How it works

### Subagents

`.claude/agents/*.md` defines each subagent with a `tools:` frontmatter whitelist. Claude Code enforces the whitelist — the subagent cannot call tools not listed, so it cannot wander outside its role, and token-heavy tool schemas for unused tools are never delivered.

Each subagent's system prompt enforces a compact report format. The orchestrator gets:

```
RESULT: done
FINDINGS:
- JWT validation: `src/auth/middleware.ts:14` uses `jsonwebtoken`
- expiry + sig checked at `:22-31`
NEXT: none
```

Rather than a three-paragraph narrative that restates the question.

### Hooks

Two Python hooks wired via the plugin's `hooks/hooks.json`:

- `grunt_log.py` — records `{tool, input_tokens, output_tokens, metadata}` per call to `.grunt/metrics.jsonl`
- `grunt_compress.py` — computes compressed form of `tool_response` and logs the delta to `.grunt/compression.jsonl`

Both are pure Python 3 standard library. No dependencies, no network calls. Everything stays local to your project's `.grunt/` directory.

Token counts are character-length-over-four estimates, suitable for relative comparison rather than billing.

### What we don't do

- **No parameter renaming.** Research showed cryptic names (`file_path` → `p`) save <2% of tokens while measurably hurting tool-call accuracy. Prompt caching on the schema is a better lever.
- **No cross-session learning.** Metrics are local, per-project, JSONL. Inspect them yourself.
- **No LLM-based rewriting.** All compression is deterministic regex/text transforms. If you can't reproduce it from the source, it doesn't happen.

## Repository layout

```
.
├── .claude-plugin/
│   └── marketplace.json        # marketplace manifest (discovered by `plugin marketplace add`)
├── agent-caveman/              # the plugin itself
│   ├── .claude-plugin/
│   │   └── plugin.json         # plugin manifest
│   ├── hooks/
│   │   ├── hooks.json          # hook registrations
│   │   ├── grunt_log.py
│   │   ├── grunt_compress.py
│   │   └── grunt_report.py
│   ├── agents/
│   │   ├── grunt-researcher.md
│   │   ├── grunt-explorer.md
│   │   └── grunt-coder.md
│   └── skills/
│       └── grunt-terse/
│           └── SKILL.md
└── README.md
```

## Status

- **Phase 1 — measurement.** Shipped.
- **Phase 2 — output compression (observer mode).** Shipped.
- **Phase 3 — per-agent tool whitelists + agent-response compression.** Shipped.
- **Phase 4 — mutation.** Pending. The compressor currently measures savings without altering what the model sees, because the Claude Code hook contract for mutating tool output is still being verified. Once confirmed, compression becomes a real token reduction.
- **Phase 5 — MCP schema wrapper.** Optional advanced path for teams wanting true per-agent schema trimming beyond whitelisting.

## License

MIT.

## Credits

Inspired by [caveman](https://github.com/JuliusBrussee/caveman) by Julius Brussee, which compresses human-facing Claude output. Agent Caveman extends the idea to the agent-to-agent channel, where prose is wasted and structure is king.
