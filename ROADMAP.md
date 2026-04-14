# Roadmap

Ideas not yet shipped, grouped by how certain we are they'll deliver. Each entry lists the lever, the expected gain, the blocker (if any), and what research would close the question.

This file is a scratchpad — edit freely, remove items once they ship or are definitively killed.

## Shipped

### PreToolUse input rewriter — `grunt_rewrite.py`

Auto-appends discipline to `WebFetch.prompt` and `Agent`/`Task.prompt` via `updatedInput`. Loose WebFetch prompts ("tell me about", "summarize", "describe" without "return only"/"code block") get a terse-extraction suffix; Agent prompts missing a response cap get a 200-word contract. Every rewrite logged to `.grunt/rewrites.jsonl` (before/after/rule). Disable with `GRUNT_REWRITE=off`. `/grunt-stats` reports counts by tool and rule.

### `/grunt-stats` diagnostics

Four heuristic warnings in the report: noisy Bash commands (>1K tok out), full-file Reads without `offset`/`limit` (>2K tok), repeated Reads (≥3× same path in a session), oversized Agent returns (>500 tok). Thresholds constants at top of `grunt_report.py`.

### GitHub MCP response compressor — `grunt_mcp_github.py`

PostToolUse hook matching `mcp__github__.*`. Parses the response JSON, drops `*_url` fields (keeps `html_url`), `node_id`, `avatar_url`, `reactions`, `author_association`, `performed_via_github_app`, etc. Compacts `user`/`assignee` objects to `{login}` and `labels` to name arrays. Typical reduction 60–75% on list payloads. Logged to `.grunt/mcp_compress.jsonl`. `GRUNT_MCP_COMPRESS=off` disables.

## High confidence, not yet built

### Linear / Postgres MCP compressors

Same pattern as `grunt_mcp_github.py` for other MCP servers. Linear responses include similar metadata bloat (`_url`, `id`, creator objects). Postgres MCP schema introspection is verbose. One compressor module per server.

### SessionStart context injection

**Lever.** Use `SessionStart` hook to inject a stable "prefer grunt-* subagents" reminder into the cached prefix. Because it's stable, it caches on turn 1.

**Gain.** Modest. Reinforces orchestrator behavior at session boundary rather than only when the skill triggers mid-session.

**Cost.** Small — one more hook, ~10 lines.

**Risk.** More text in every session even when multi-agent work isn't happening. Consider gating on project markers.

## Lower confidence / speculative

### Subagent response length enforcement

**Lever.** PostToolUse on Agent tool — if the response exceeds a threshold, use `decision: "block"` with a reason asking for a shorter retry.

**Gain.** Real enforcement of the "max 200 words" contract.

**Risk.** Loops if the subagent repeatedly fails the cap. Need retry limit logic.

**Cost.** Medium — needs careful design to avoid infinite loops.

### Tool-choice narrowing via PreToolUse block

**Lever.** PreToolUse on `Agent` with `subagent_type: general-purpose` — if the task description matches a `grunt-*` role, block and suggest the specialist.

**Gain.** Forces routing discipline at the call site instead of hoping the orchestrator skill kicks in.

**Risk.** Over-blocking; annoying if heuristic misfires.

**Cost.** Medium.

### Prompt cache breakpoint optimization

**Lever.** Audit our skill/agent content for stability across turns. Any dynamic content (timestamps, randomized examples) busts the prefix cache.

**Gain.** Unknown — likely small. Claude Code handles most caching automatically.

**Cost.** Research only.

## Definitively killed

### Stop / SubagentStop transcript mutation
Both hooks are observation-only. They fire *after* response generation completes and cannot modify messages already sent to the parent. `additionalContext` adds to the *next* turn (increasing cost, not reducing it). Source: https://code.claude.com/docs/en/hooks.md

### Built-in tool output mutation via PostToolUse
Claude Code's `updatedMCPToolOutput` is MCP-only. Built-ins are immutable via the public hook contract.

### MCP wrapper of built-in tools
Would disable Claude Code's permission enforcement (Edit's "must Read first" rule). Modest schema savings not worth the security regression.

### Parameter renaming (`file_path` → `p`)
<2% savings per Anthropic's own tokenizer, measurable accuracy cost on tool argument filling.

### LLM-based rewriting of tool output
Would add a token-spending LLM call to save tokens. Break-even at best. Deterministic regex is the right floor.
