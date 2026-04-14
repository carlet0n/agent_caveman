#!/usr/bin/env python3
"""Grunt metrics report. Reads .grunt/metrics.jsonl → prints summary."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import grunt_transcript


# Rough schema footprint: empirically Claude Code's built-in tool schemas
# average ~300 tok each once you include description + parameters JSON Schema.
# A general-purpose subagent inherits ~15 built-in tools; each grunt-* subagent
# whitelists a subset, so the delta = (15 - whitelist_size) * AVG_SCHEMA_TOK.
# Number is an estimate — exact schemas vary by Claude Code version.
AVG_SCHEMA_TOK = 300
GENERAL_PURPOSE_TOOLS = 15


def _parse_whitelist(agent_md: Path) -> list[str]:
    try:
        txt = agent_md.read_text(encoding="utf-8")
    except OSError:
        return []
    lines = txt.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("tools:"):
            return [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
    return []


def _schema_savings_report(plugin_dir: Path) -> list[str]:
    agents_dir = plugin_dir / "agents"
    if not agents_dir.exists():
        return []
    lines = []
    for f in sorted(agents_dir.glob("*.md")):
        tools = _parse_whitelist(f)
        if not tools:
            continue
        skipped = max(0, GENERAL_PURPOSE_TOOLS - len(tools))
        saved_tok = skipped * AVG_SCHEMA_TOK
        lines.append(
            f"  {f.stem:<22} tools={len(tools):<2} skipped≈{skipped} × "
            f"{AVG_SCHEMA_TOK}tok = ~{saved_tok} tok saved per spawn"
        )
    return lines


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent.parent


def load(path: Path, session: str | None):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if session and r.get("session") != session:
            continue
        rows.append(r)
    return rows


NOISY_BASH_TOK = 1000
FULL_READ_TOK = 2000
OVERSIZED_AGENT_TOK = 500
REPEAT_READ_N = 3
TOP_DIAG = 5


def _print_diagnostics(rows: list) -> None:
    noisy: list[tuple[str, int]] = []
    full_reads: list[tuple[str, int]] = []
    big_agents: list[tuple[str, str, int]] = []
    reads_by_path: dict[str, int] = defaultdict(int)

    pre_read_scoped: dict[tuple[float, str], bool] = {}

    for r in rows:
        tool = r.get("tool")
        ev = r.get("event")
        if tool == "Read" and ev == "PreToolUse":
            pre_read_scoped[(round(r.get("ts", 0), 2), r.get("path", ""))] = bool(
                r.get("scoped")
            )
            reads_by_path[r.get("path", "")] += 1
        elif tool == "Read" and ev == "PostToolUse":
            out = r.get("out_tok", 0)
            path = r.get("path", "")
            scoped = None
            for (ts, p), s in pre_read_scoped.items():
                if p == path and abs(ts - round(r.get("ts", 0), 2)) < 2:
                    scoped = s
                    break
            if scoped is False and out > FULL_READ_TOK:
                full_reads.append((path, out))
        elif tool == "Bash" and ev == "PostToolUse":
            if r.get("out_tok", 0) > NOISY_BASH_TOK:
                noisy.append((r.get("cmd", "?"), r.get("out_tok", 0)))
        elif tool == "Agent" and ev == "PostToolUse":
            if r.get("out_tok", 0) > OVERSIZED_AGENT_TOK:
                big_agents.append(
                    (r.get("subagent", "?"), r.get("agent_desc", ""), r.get("out_tok", 0))
                )

    if noisy:
        print(f"\nnoisy Bash (>{NOISY_BASH_TOK} tok out):")
        for cmd, tok in sorted(noisy, key=lambda x: -x[1])[:TOP_DIAG]:
            print(f"  {tok:>6} tok  {cmd}")

    if full_reads:
        print(f"\nfull-file Reads (>{FULL_READ_TOK} tok, no offset/limit):")
        for path, tok in sorted(full_reads, key=lambda x: -x[1])[:TOP_DIAG]:
            print(f"  {tok:>6} tok  {path}")

    repeated = [(p, n) for p, n in reads_by_path.items() if n >= REPEAT_READ_N]
    if repeated:
        print(f"\nrepeated Reads (≥{REPEAT_READ_N}× same file):")
        for p, n in sorted(repeated, key=lambda x: -x[1])[:TOP_DIAG]:
            print(f"  n={n:>3}  {p}")

    if big_agents:
        print(f"\noversized subagent returns (>{OVERSIZED_AGENT_TOK} tok):")
        for name, desc, tok in sorted(big_agents, key=lambda x: -x[2])[:TOP_DIAG]:
            print(f"  {tok:>6} tok  {name:<22} {desc}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", help="filter by session id")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument(
        "--no-transcript",
        action="store_true",
        help="skip authoritative usage readout from Claude Code session transcript",
    )
    args = ap.parse_args()

    root = project_root()
    if not args.no_transcript:
        tdir = grunt_transcript.transcript_dir(root)
        totals = grunt_transcript.aggregate(tdir, args.session)
        print(grunt_transcript.format_report(totals))
        print()

    rows = load(root / ".grunt" / "metrics.jsonl", args.session)
    if not rows:
        print("no hook metrics yet. run some tool calls first.")
        return 0
    print("--- hook-observed tool usage (char/4 estimates) ---")

    # Pair Pre/Post by (session, tool, nearest timestamp). Simpler: treat each row
    # independently — PreToolUse gives input cost, PostToolUse gives output cost.
    in_by_tool: dict[str, int] = defaultdict(int)
    out_by_tool: dict[str, int] = defaultdict(int)
    calls_by_tool: dict[str, int] = defaultdict(int)
    subagent_cost: dict[str, list[int]] = defaultdict(list)

    for r in rows:
        tool = r.get("tool") or "?"
        if r.get("event") == "PreToolUse":
            in_by_tool[tool] += r.get("in_tok", 0)
            calls_by_tool[tool] += 1
        elif r.get("event") == "PostToolUse":
            out_by_tool[tool] += r.get("out_tok", 0)
        if tool == "Agent" and r.get("event") == "PostToolUse":
            subagent_cost[r.get("subagent", "?")].append(r.get("out_tok", 0))

    total_in = sum(in_by_tool.values())
    total_out = sum(out_by_tool.values())
    print(f"sessions rows: {len(rows)}  total in≈{total_in} tok  out≈{total_out} tok")
    print()

    tools = sorted(
        set(in_by_tool) | set(out_by_tool),
        key=lambda t: -(in_by_tool[t] + out_by_tool[t]),
    )[: args.top]
    print(f"{'tool':<20}{'calls':>8}{'in_tok':>10}{'out_tok':>10}{'avg_out':>10}")
    for t in tools:
        n = calls_by_tool[t] or 1
        print(
            f"{t:<20}{calls_by_tool[t]:>8}{in_by_tool[t]:>10}{out_by_tool[t]:>10}"
            f"{out_by_tool[t]//n:>10}"
        )

    if subagent_cost:
        print("\nsubagent return cost (tok per call):")
        for name, costs in subagent_cost.items():
            avg = sum(costs) // len(costs)
            print(f"  {name:<20} n={len(costs)} avg={avg} max={max(costs)}")

    _print_diagnostics(rows)

    rw_path = root / ".grunt" / "rewrites.jsonl"
    if rw_path.exists():
        by_rule: dict[str, int] = defaultdict(int)
        by_tool: dict[str, int] = defaultdict(int)
        added_chars = 0
        for line in rw_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.session and r.get("session") != args.session:
                continue
            by_rule[r.get("rule", "?")] += 1
            by_tool[r.get("tool", "?")] += 1
            added_chars += int(r.get("added_chars") or 0)
        total = sum(by_rule.values())
        if total:
            print(
                f"\nprompt rewrites applied: {total} "
                f"(+{added_chars} chars ≈ +{added_chars // 4} input tok; "
                f"pays for itself when downstream response shrinks more)"
            )
            for tool, n in sorted(by_tool.items(), key=lambda kv: -kv[1]):
                print(f"  {tool:<20} n={n}")
            for rule, n in sorted(by_rule.items(), key=lambda kv: -kv[1]):
                print(f"  rule={rule:<20} n={n}")

    plugin_dir = Path(__file__).resolve().parent.parent
    savings = _schema_savings_report(plugin_dir)
    if savings:
        print("\nsubagent schema footprint (estimated, vs general-purpose):")
        for line in savings:
            print(line)

    mcp_path = root / ".grunt" / "mcp_compress.jsonl"
    if mcp_path.exists():
        saved_chars = 0
        calls = 0
        by_tool_mcp: dict[str, int] = defaultdict(int)
        for line in mcp_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.session and r.get("session") != args.session:
                continue
            calls += 1
            s = int(r.get("saved_chars") or 0)
            saved_chars += s
            by_tool_mcp[r.get("tool", "?")] += s
        if calls:
            print(
                f"\nMCP response compression: {calls} calls, "
                f"saved {saved_chars} chars ≈ {saved_chars // 4} output tok"
            )
            for tool, s in sorted(by_tool_mcp.items(), key=lambda kv: -kv[1])[:5]:
                print(f"  {tool:<30} {s:>8} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
