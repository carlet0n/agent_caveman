#!/usr/bin/env python3
"""PreToolUse hook: rewrite loose WebFetch and Agent prompts to enforce
token discipline automatically. Uses Claude Code's `updatedInput` mechanism.

Every rewrite is logged to .grunt/rewrites.jsonl (before / after / rule) so
users can audit exactly what changed and why.

Disable with env var GRUNT_REWRITE=off.

Contract reference:
    https://code.claude.com/docs/en/hooks.md
    Output shape for mutation:
    {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "updatedInput": {...full input with modifications...}
    }}
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent.parent


# --- WebFetch rules --------------------------------------------------------

# Prompts that ask for prose about the page ("tell me about", "what is", etc.)
# without any discipline markers. Case-insensitive, matched against the prompt
# as a whole; we don't try to parse natural language.
WEBFETCH_LOOSE_RE = re.compile(
    r"\b(tell me about|what (?:is|are|does)|summarize|describe|explain|"
    r"give (?:me )?(?:a |an )?(?:overview|summary)|how does)\b",
    re.IGNORECASE,
)

# Discipline markers — if any of these are present, leave the prompt alone.
WEBFETCH_DISCIPLINE_RE = re.compile(
    r"\b(return only|code block(?:\s+only)?|no prose|no preamble|"
    r"max \d+ words?|under \d+ words?|one line|single line|"
    r"just the|only the|verbatim)\b",
    re.IGNORECASE,
)

WEBFETCH_SUFFIX = (
    "\n\nReturn only the key facts. No preamble, no closing. "
    "If a specific value, code block, or command is asked for, output only that. "
    "Max 100 words."
)


# --- Agent rules -----------------------------------------------------------

# Agent prompts without any response-size cap.
AGENT_CAP_RE = re.compile(
    r"\b(max \d+ words?|under \d+ words?|no more than \d+ words?|"
    r"brief(?:ly)?|terse|short(?:\s+response)?|one line|single line|"
    r"RESULT:|FINDINGS:)\b",
    re.IGNORECASE,
)

AGENT_SUFFIX = (
    "\n\nResponse contract: max 200 words, no preamble or closing pleasantries. "
    "Lead with the answer. Use structured bullets over prose where possible."
)


# --- Core ------------------------------------------------------------------

def rewrite_webfetch(inp: dict) -> tuple[dict, str | None]:
    """Return (updated_input, rule_name_or_None)."""
    prompt = inp.get("prompt") or ""
    if not prompt:
        return inp, None
    if WEBFETCH_DISCIPLINE_RE.search(prompt):
        return inp, None
    if not WEBFETCH_LOOSE_RE.search(prompt):
        return inp, None
    new = dict(inp)
    new["prompt"] = prompt.rstrip() + WEBFETCH_SUFFIX
    return new, "webfetch-loose"


def rewrite_agent(inp: dict) -> tuple[dict, str | None]:
    prompt = inp.get("prompt") or ""
    if not prompt:
        return inp, None
    if AGENT_CAP_RE.search(prompt):
        return inp, None
    new = dict(inp)
    new["prompt"] = prompt.rstrip() + AGENT_SUFFIX
    return new, "agent-no-cap"


REWRITERS = {
    "WebFetch": rewrite_webfetch,
    "Agent": rewrite_agent,
    "Task": rewrite_agent,  # alternate name for the Agent tool
}


def log_rewrite(session: str, tool: str, rule: str, before: str, after: str) -> None:
    out_dir = project_root() / ".grunt"
    out_dir.mkdir(exist_ok=True)
    rec = {
        "ts": time.time(),
        "session": session,
        "tool": tool,
        "rule": rule,
        "before_prompt": before,
        "after_prompt": after,
        "added_chars": len(after) - len(before),
    }
    with (out_dir / "rewrites.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    if os.environ.get("GRUNT_REWRITE", "").lower() in ("off", "0", "false", "no"):
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    raw = sys.stdin.read()
    try:
        evt = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    if evt.get("hook_event_name") != "PreToolUse":
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    tool = evt.get("tool_name", "")
    inp = evt.get("tool_input")
    if not isinstance(inp, dict):
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    rewriter = REWRITERS.get(tool)
    if not rewriter:
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    new_input, rule = rewriter(inp)
    if rule is None:
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    log_rewrite(
        evt.get("session_id", ""),
        tool,
        rule,
        inp.get("prompt", ""),
        new_input.get("prompt", ""),
    )

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": new_input,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
