#!/usr/bin/env python3
"""Static upper-bound on subagent tool-schema savings.

Reads each `agent-caveman/agents/*.md` frontmatter, extracts the `tools:`
whitelist, and compares against Claude Code's default subagent toolset
(`general-purpose`, ~15 tools). Claude Code ships the JSON schema for each
tool on every subagent turn that isn't served from prompt cache, so this
tool-count delta is the ceiling on whitelist savings.

Typical per-tool JSON schema weight (descriptions + params) is ~1-3KB, so
the raw byte delta is approximately `(tool_count_delta) × 2KB`. Actual
savings depend on cache hit rate — cache_creation pays the full delta,
cache_read pays ~10%.

Usage:
  python3 bench/schema_size.py
"""
from __future__ import annotations

import re
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / "agents"

# Approximate tool list shipped to `general-purpose` (Claude Code default).
# Sourced from the Agent tool's tool-schemas as of 2026-04.
GENERAL_PURPOSE_TOOLS = [
    "Bash", "Edit", "Glob", "Grep", "Read", "Write",
    "NotebookEdit", "WebFetch", "WebSearch", "TodoWrite",
    "Task", "ExitPlanMode", "BashOutput", "KillShell",
    "SlashCommand",
]
APPROX_BYTES_PER_TOOL = 2000  # rough JSON schema weight


def parse_tools(md_path: Path) -> list[str]:
    text = md_path.read_text(encoding="utf-8")
    m = re.search(r"^tools:\s*(.+)$", text, re.M)
    if not m:
        return []
    raw = m.group(1).strip()
    return [t.strip() for t in raw.split(",") if t.strip()]


def main() -> int:
    gp_n = len(GENERAL_PURPOSE_TOOLS)
    gp_bytes = gp_n * APPROX_BYTES_PER_TOOL
    print(f"{'subagent':<24} {'tools':>6} {'≈schema_bytes':>15}  {'Δ vs general':>14}")
    print("-" * 68)
    print(f"{'general-purpose':<24} {gp_n:>6} {gp_bytes:>15}  {'0':>14}")
    for md in sorted(AGENTS_DIR.glob("*.md")):
        tools = parse_tools(md)
        n = len(tools)
        b = n * APPROX_BYTES_PER_TOOL
        delta = b - gp_bytes
        pct = (delta / gp_bytes * 100) if gp_bytes else 0
        print(
            f"{md.stem:<24} {n:>6} {b:>15}  {delta:>+8} ({pct:+5.1f}%)"
        )
    print()
    print("Savings model:")
    print("  cache_creation delta ≈ |Δ schema_bytes| per spawn (≈bytes/4 tok)")
    print("  cache_read    delta ≈ 10% of that per turn after first")
    print("  Net ≈ (spawns × cache_creation_delta) + (turns × cache_read_delta)")
    print()
    print(f"Per-tool byte approximation: {APPROX_BYTES_PER_TOOL} bytes.")
    print("Calibrate by inspecting one subagent's system_message in the")
    print("Claude Code session transcript (~/.claude/projects/...jsonl).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
