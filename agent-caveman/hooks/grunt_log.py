#!/usr/bin/env python3
"""Grunt Phase 1: log token cost per tool call to JSONL.

Reads Claude Code hook JSON on stdin. Emits one JSONL record per event into
.grunt/metrics.jsonl at the project root. Token counts are char/4 estimates —
good enough for relative comparison, not billing.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


_TOKENIZER_CACHE: dict = {}


def _get_tokenizer():
    """Return a callable(str) -> int, or None to fall back to char/4.

    Controlled by GRUNT_TOKENIZER:
      unset | "char4"   char count / 4 (default, no deps)
      "tiktoken"        tiktoken cl100k_base (rough Anthropic proxy)
      "anthropic"       anthropic.Anthropic().beta.messages.count_tokens
    """
    if "fn" in _TOKENIZER_CACHE:
        return _TOKENIZER_CACHE["fn"]
    mode = (os.environ.get("GRUNT_TOKENIZER") or "char4").lower()
    fn = None
    if mode == "tiktoken":
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("cl100k_base")
            fn = lambda s: len(enc.encode(s))  # noqa: E731
        except Exception:
            fn = None
    elif mode == "anthropic":
        try:
            import anthropic  # type: ignore

            client = anthropic.Anthropic()
            fn = lambda s: client.beta.messages.count_tokens(  # noqa: E731
                model="claude-opus-4-6",
                messages=[{"role": "user", "content": s}],
            ).input_tokens
        except Exception:
            fn = None
    _TOKENIZER_CACHE["fn"] = fn
    return fn


def estimate_tokens(obj) -> int:
    if obj is None:
        return 0
    if isinstance(obj, str):
        s = obj
    else:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    tok = _get_tokenizer()
    if tok is not None:
        try:
            return max(1, int(tok(s)))
        except Exception:
            pass
    return max(1, len(s) // 4)


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent


def main() -> int:
    raw = sys.stdin.read()
    try:
        evt = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        evt = {"_parse_error": raw[:200]}

    event_name = evt.get("hook_event_name", "unknown")
    tool_name = evt.get("tool_name", "")
    tool_input = evt.get("tool_input")
    tool_response = evt.get("tool_response")

    record = {
        "ts": time.time(),
        "event": event_name,
        "session": evt.get("session_id", ""),
        "tool": tool_name,
        "in_tok": estimate_tokens(tool_input) if tool_input is not None else 0,
        "out_tok": estimate_tokens(tool_response) if tool_response is not None else 0,
    }

    # Per-tool extras useful for slicing later.
    if isinstance(tool_input, dict):
        if tool_name == "Agent":
            record["subagent"] = tool_input.get("subagent_type", "general-purpose")
            record["agent_desc"] = tool_input.get("description", "")[:80]
        elif tool_name in ("Bash",):
            record["cmd"] = (tool_input.get("command") or "")[:120]
        elif tool_name in ("Read", "Edit", "Write"):
            record["path"] = tool_input.get("file_path", "")
            if tool_name == "Read":
                record["scoped"] = (
                    tool_input.get("offset") is not None
                    or tool_input.get("limit") is not None
                )

    out_dir = project_root() / ".grunt"
    out_dir.mkdir(exist_ok=True)
    with (out_dir / "metrics.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Don't block or mutate — just observe.
    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
