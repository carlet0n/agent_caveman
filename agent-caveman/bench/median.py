#!/usr/bin/env python3
"""Aggregate bench/history.jsonl by label and print medians.

Groups rows by the task-name stem of `label` (strips trailing `-YYYYMMDD-HHMMSS`
and `-rep<N>` suffixes). For each group, prints median baseline/treatment token
totals and the delta. Medians are robust to the non-determinism noted in
bench/README.md.

Usage:
  python3 bench/median.py
  python3 bench/median.py --path bench/history.jsonl
  python3 bench/median.py --label webfetch_summary
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent / "history.jsonl"
_STEM_RE = re.compile(r"(?:-rep\d+)?(?:-\d{8}-\d{6})?$")


def _stem(label: str) -> str:
    return _STEM_RE.sub("", label or "") or "?"


def _pct(a: float, b: float) -> str:
    if not a:
        return "    n/a"
    return f"{(b - a) / a * 100:+6.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--label", default=None, help="filter to stems containing this substring")
    args = ap.parse_args()

    if not args.path.exists():
        print(f"no history yet: {args.path}")
        return 0

    groups: dict[str, list[dict]] = defaultdict(list)
    for line in args.path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        stem = _stem(r.get("label") or "")
        if args.label and args.label not in stem:
            continue
        groups[stem].append(r)

    if not groups:
        print("(no matching rows)")
        return 0

    hdr = (
        f"{'task':<28} {'n':>3}  {'med_base_in':>11} {'med_treat_in':>12} {'Δin%':>8}"
        f"  {'med_base_out':>12} {'med_treat_out':>13} {'Δout%':>8}  {'rw_avg':>6}"
    )
    print(hdr)
    print("-" * len(hdr))
    for stem in sorted(groups):
        rows = groups[stem]
        n = len(rows)
        base_in = [int((r.get("baseline") or {}).get("total_input", 0)) for r in rows]
        treat_in = [int((r.get("treatment") or {}).get("total_input", 0)) for r in rows]
        base_out = [int((r.get("baseline") or {}).get("output_tokens", 0)) for r in rows]
        treat_out = [int((r.get("treatment") or {}).get("output_tokens", 0)) for r in rows]
        rw = [int((r.get("rewrites") or {}).get("treatment", 0)) for r in rows]
        mbi, mti = statistics.median(base_in), statistics.median(treat_in)
        mbo, mto = statistics.median(base_out), statistics.median(treat_out)
        print(
            f"{stem[:28]:<28} {n:>3}  {int(mbi):>11} {int(mti):>12} {_pct(mbi, mti):>8}"
            f"  {int(mbo):>12} {int(mto):>13} {_pct(mbo, mto):>8}  {statistics.mean(rw):>6.1f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
