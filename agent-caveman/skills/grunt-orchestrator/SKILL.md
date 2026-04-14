---
name: grunt-orchestrator
description: Use when spawning subagents, delegating research, or calling WebFetch. Picks the right specialized subagent over general-purpose, and forces tight extraction prompts on web fetches. Triggers on "multi-agent workflow", "delegate", "spawn subagent", "research this", "fetch", "summarize this URL", "look up".
---

# Grunt Orchestrator

Two jobs, both source-side token control:

1. Route delegation to the tightest subagent that fits
2. Write WebFetch / research prompts that ask for the answer, not the page

## 1. Subagent routing

Pick the narrowest role. `general-purpose` is the fallback, not the default.

| Task pattern                                  | Use                 |
|-----------------------------------------------|---------------------|
| "look up docs", "find prior art", web search  | `grunt-researcher`  |
| "where is X in the code", "how does X work"   | `grunt-explorer`    |
| "edit file Y to do Z" (with spec ready)       | `grunt-coder`       |
| Task spans roles or needs all tools           | `general-purpose`   |
| Task touches plugins/hooks/skills/API details | `claude-code-guide` |

Each `grunt-*` agent ships a strict output contract (`RESULT / FINDINGS / FILES / NEXT`) — you'll get structured facts, not prose. That's the point.

When briefing any subagent:

- State the goal in one sentence
- List what's already ruled out
- Hand over exact paths/URLs/commands when known
- Cap response length explicitly (`max 200 words`)
- State whether code changes are expected or read-only

## 2. WebFetch prompts

Data from this project: WebFetch averages **~7,200 output tokens per call** when prompts are vague. Tight prompts cut that by an order of magnitude — the underlying small model generates only what you asked for.

Rule: **ask for the extract, not a summary of the page.**

| Bad prompt                                     | Better prompt                                                                                |
|------------------------------------------------|----------------------------------------------------------------------------------------------|
| "What does this page say about plugins?"       | "Return only the minimal `plugin.json` required fields as a JSON code block. No prose."     |
| "Tell me about the MCP protocol."              | "List the exact names of the four MCP primitives (tools/resources/prompts/sampling). Name only, one per line." |
| "Summarize Anthropic's hook documentation."    | "Return the exact JSON shape a PostToolUse hook emits to mutate tool output. Code block only." |
| "What's the install command?"                  | "Return only the shell command to install this as a Claude Code plugin. One line."           |

Patterns that keep WebFetch responses small:

- "Return only..." / "One line." / "No prose." / "Code block only."
- Ask for a specific field, schema, command, or URL — not an explanation
- If you need prose, cap words: "Max 40 words, no preamble."
- Name the output format: JSON, table, bullet list of ≤5 items

Before calling WebFetch, ask yourself: *what would the ideal response look like?* Then demand exactly that.

## Anti-patterns

- Spawning `general-purpose` when `grunt-explorer` fits — loads every tool's schema into the subagent's context
- Asking a subagent to "explore and tell me what you find" — returns narrative, not facts
- WebFetch prompts phrased as questions ("What is X?") — the model answers conversationally, long
- Forgetting to cap response length when delegating — subagents default to thorough prose

## When to ignore this skill

- Task is trivial, single tool call, done inline — no delegation needed
- User explicitly asked for full prose / teaching tone — compression disserves them
- Security warnings, destructive ops, confirmations — clarity beats brevity
