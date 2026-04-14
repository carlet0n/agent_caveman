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


def estimate_tokens(obj) -> int:
    if obj is None:
        return 0
    if isinstance(obj, str):
        s = obj
    else:
        s = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
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

    out_dir = project_root() / ".grunt"
    out_dir.mkdir(exist_ok=True)
    with (out_dir / "metrics.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Don't block or mutate — just observe.
    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
