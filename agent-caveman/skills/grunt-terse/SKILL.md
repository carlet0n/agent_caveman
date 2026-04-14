---
name: grunt-terse
description: Invoke before spawning subagents, or have subagents invoke before returning their final report. Forces caveman-style compact output for agent↔agent handoffs to cut tokens on inter-agent channel. Use when orchestrating multi-agent workflows, delegating research tasks, or when a subagent is about to summarize findings back to the caller.
---

# Grunt Terse — compact agent↔agent reports

Goal: cut tokens on the inter-agent channel. Subagent prose is wasted on orchestrator — orchestrator wants facts, paths, line numbers, next step. Not narrative.

## When subagent reports back

Structure final message as fragments. No preamble. No "I investigated...". No closing summary.

### Required fields (in order)

```
RESULT: <one line — done | partial | blocked>
FINDINGS:
- <fact with path:line when code>
- <fact>
FILES: <comma list of paths touched or relevant>
NEXT: <one line — what caller should do, or "none">
```

Omit any section with nothing to say. No empty headers.

### Rules

- Drop articles (a/the/an), filler (just/really/basically), pleasantries
- Fragments OK. `[thing] [action] [reason]` pattern
- Quote errors exact, inside backticks
- Keep code blocks, commands, paths, flags **unchanged** — never abbreviate technical substance
- Line/file refs as `path/to/file.py:42` so caller can click
- No "let me know if..." / "happy to..." / "hope this helps"
- Max ~150 words unless caller asked for full content

### Examples

❌ Verbose:
> I searched through the codebase and found that authentication is handled in src/auth/middleware.ts. The file defines a middleware function that validates JWT tokens using the jsonwebtoken library. It checks for token expiry and signature validity. There's also a helper in src/auth/utils.ts that handles token refresh. Let me know if you'd like me to investigate further!

✅ Terse:
> RESULT: done
> FINDINGS:
> - JWT validation: `src/auth/middleware.ts:14` uses `jsonwebtoken`
> - expiry + sig checked at `:22-31`
> - refresh helper: `src/auth/utils.ts:8`
> NEXT: none

## When orchestrator delegates

Brief subagent terse too:

- State goal in one sentence
- List what's already ruled out (don't make them re-derive)
- Hand over exact paths / commands when known
- Cap response length explicitly ("report <150 words")
- Say whether code changes expected or research only

## Exceptions (don't compress)

- Security warnings, destructive-op confirmations — write normal
- When caller explicitly asks for full prose / teaching tone
- Error messages, logs, stack traces — quote verbatim
