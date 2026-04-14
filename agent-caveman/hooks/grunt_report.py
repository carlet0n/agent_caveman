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

    # Compression savings.
    comp_path = project_root() / ".grunt" / "compression.jsonl"
    if comp_path.exists():
        orig_by_tool: dict[str, int] = defaultdict(int)
        saved_by_tool: dict[str, int] = defaultdict(int)
        n_by_tool: dict[str, int] = defaultdict(int)
        for line in comp_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if args.session and r.get("session") != args.session:
                continue
            t = r.get("tool") or "?"
            orig_by_tool[t] += r.get("orig_tok", 0)
            saved_by_tool[t] += r.get("saved_tok", 0)
            n_by_tool[t] += 1
        total_orig = sum(orig_by_tool.values())
        total_saved = sum(saved_by_tool.values())
        if total_orig:
            pct = 100 * total_saved / total_orig
            print(
                f"\ncompression potential: {total_saved}/{total_orig} tok saved "
                f"({pct:.1f}%)"
            )
            for t, orig in sorted(orig_by_tool.items(), key=lambda kv: -kv[1]):
                s = saved_by_tool[t]
                p = 100 * s / orig if orig else 0
                print(f"  {t:<20} n={n_by_tool[t]:<4} {s}/{orig} ({p:.1f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
