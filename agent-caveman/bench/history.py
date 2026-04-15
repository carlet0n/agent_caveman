#!/usr/bin/env python3
"""Display bench/history.jsonl as a table.

Each row is one compare invocation. Shows treatment vs baseline deltas over time
so you can see whether plugin savings are trending the right way.

Usage:
  python3 bench/history.py                 # show all rows
  python3 bench/history.py --label webfetch_summary
  python3 bench/history.py --tail 20
  python3 bench/history.py --json          # raw JSONL pass-through
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "history.jsonl"


def _pct(a: int, b: int) -> str:
    if not a:
        return "    n/a"
    return f"{(b - a) / a * 100:+6.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--label", default=None, help="filter to rows whose label contains this substring")
    ap.add_argument("--tail", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="print raw JSONL")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"no history yet: {args.path}")
        return 0

    rows = []
    for line in args.path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    if args.label:
        rows = [r for r in rows if args.label in (r.get("label") or "")]
    if args.tail:
        rows = rows[-args.tail :]

    if args.json:
        for r in rows:
            print(json.dumps(r))
        return 0

    if not rows:
        print("(no matching rows)")
        return 0

    hdr = f"{'ts':<20} {'label':<34} {'base_in':>9} {'treat_in':>9} {'Δin%':>8} {'base_out':>9} {'treat_out':>9} {'Δout%':>8} {'rw':>5}"
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        ts = (r.get("ts") or "")[:19]
        label = (r.get("label") or "")[:34]
        b = r.get("baseline") or {}
        t = r.get("treatment") or {}
        bi, ti = int(b.get("total_input", 0)), int(t.get("total_input", 0))
        bo, to = int(b.get("output_tokens", 0)), int(t.get("output_tokens", 0))
        rw = (r.get("rewrites") or {}).get("treatment", 0)
        print(f"{ts:<20} {label:<34} {bi:>9} {ti:>9} {_pct(bi, ti):>8} {bo:>9} {to:>9} {_pct(bo, to):>8} {rw:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
