#!/usr/bin/env python3
"""Grunt metrics report. Reads .grunt/metrics.jsonl → prints summary."""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


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
    args = ap.parse_args()

    rows = load(project_root() / ".grunt" / "metrics.jsonl", args.session)
    if not rows:
        print("no metrics yet. run some tool calls first.")
        return 0

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

    rw_path = project_root() / ".grunt" / "rewrites.jsonl"
    if rw_path.exists():
        by_rule: dict[str, int] = defaultdict(int)
        by_tool: dict[str, int] = defaultdict(int)
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
        total = sum(by_rule.values())
        if total:
            print(f"\nprompt rewrites applied: {total}")
            for tool, n in sorted(by_tool.items(), key=lambda kv: -kv[1]):
                print(f"  {tool:<20} n={n}")
            for rule, n in sorted(by_rule.items(), key=lambda kv: -kv[1]):
                print(f"  rule={rule:<20} n={n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
