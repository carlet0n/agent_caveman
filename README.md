# Agent Caveman

Token-efficient multi-agent workflows for Claude Code.

Caveman makes humans talk to Claude in fewer tokens. Agent Caveman makes *Claude talk to Claude* in fewer tokens — the orchestrator-to-subagent channel that multi-agent workflows burn through invisibly.

## What it does

When you run multi-agent workflows in Claude Code (spawning subagents via the `Agent`/`Task` tool), three things quietly eat tokens:

1. **Subagent responses** — long narrative reports where the orchestrator only needed the facts
2. **WebFetch responses** — in real sessions, WebFetch averages ~7,000 tokens per call and often dominates total token spend; disciplined extraction prompts cut that by an order of magnitude
3. **Tool schemas** — the full tool list shipped to every subagent, even tools the subagent will never call

Agent Caveman attacks all three at the **source**: opinionated subagent definitions with minimal tool whitelists, a strict output contract in each subagent's system prompt, and a skill that teaches the lead agent to route to the right subagent and write tight WebFetch prompts. Hooks measure what each tool call actually costs so you can see what's working.

This is not a transport-layer compressor. Claude Code's public hook contract does not allow rewriting the output of built-in tools before the model consumes it, so we don't pretend to. Every reduction you see comes from generating less in the first place.

## Install

One line, no approval gate — Claude Code plugin marketplaces install from any public GitHub repo directly:

```bash
claude plugin marketplace add carlet0n/agent_caveman && claude plugin install agent-caveman@agent-caveman
```

That's it. No mode to enable, no level to pick, no configuration. The `grunt-*` subagents become available to the orchestrator and the measurement hooks register automatically.

> Anthropic does not gate or review user marketplaces — any public GitHub repo works. (There is a separate opt-in curated marketplace Anthropic runs, which accepts submissions via `claude.ai/settings/plugins/submit`.)

### Local development install

To hack on the plugin, point Claude Code at a working copy:

```bash
git clone https://github.com/carlet0n/agent_caveman.git
cd agent_caveman
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

Each ships a strict output contract in its system prompt (`RESULT / FINDINGS / FILES / NEXT` blocks), so returns are structured facts rather than prose. The tool whitelists shrink the schema payload delivered to each subagent — they cannot call tools not listed, and Claude Code does not ship descriptions for tools the subagent lacks.

**2. Orchestrator + subagent skills.** Two skills load on-demand:

- `grunt-orchestrator` — triggers when the lead agent spawns subagents or calls WebFetch. Provides a task-to-subagent routing table and teaches tight extraction prompts ("Return only X as a code block" instead of "Tell me about X"). WebFetch responses shrink dramatically when the prompt asks for the answer, not a summary of the page.
- `grunt-terse` — can be invoked by any subagent before returning a final report to enforce the `RESULT / FINDINGS / NEXT` format.

**3. Measurement.** A `PreToolUse`/`PostToolUse` pair writes one JSONL record per tool call to `.grunt/metrics.jsonl` in whichever project you're working in. Check your spend in-session:

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
  grunt-*              (structured reports, avg ~250)
```

Filter by session with `--session <id>`.

The numbers are character-length-over-four estimates — suitable for comparison across sessions, not for billing.

## How it works

### Subagents

`agent-caveman/agents/*.md` defines each subagent with a `tools:` frontmatter whitelist. Claude Code enforces the whitelist, so each subagent's system context only carries schemas for the tools it can actually use.

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

One measurement hook wired via the plugin's `hooks/hooks.json`:

- `grunt_log.py` — records `{tool, input_tokens, output_tokens, metadata}` per call to `.grunt/metrics.jsonl`

Pure Python 3 standard library. No dependencies, no network calls. Everything stays local to your project's `.grunt/` directory.

### What we don't do

- **No built-in tool output mutation.** Claude Code's hook contract only allows rewriting MCP tool responses (`updatedMCPToolOutput`). Built-in tools — Bash, Read, Edit, WebFetch, Agent — cannot be rewritten before the model sees them. A "compressor" that modified them would be silently ignored, so we don't ship one. All savings are at the source.
- **No MCP wrapper of built-in tools.** Could technically bypass the above, but wrapping Edit/Read behind our own server disables Claude Code's permission enforcement (e.g. Edit's "must Read first" rule). Not worth the security regression for modest schema savings.
- **No parameter renaming.** Research showed cryptic names (`file_path` → `p`) save <2% of tokens while measurably hurting tool-call accuracy.
- **No LLM-based rewriting.** Every reduction is deterministic and inspectable.
- **No cross-session learning.** Metrics stay local, per-project, JSONL. Inspect them yourself.

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

## License

MIT.

## Credits

Inspired by [caveman](https://github.com/JuliusBrussee/caveman) by Julius Brussee, which compresses human-facing Claude output. Agent Caveman extends the idea to the agent-to-agent channel, where prose is wasted and structure is king.
