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
        f"{'task':<24} {'n':>3}  {'med_Δin':>8} {'IQR_Δin':>9}  {'med_Δout':>9} {'IQR_Δout':>9}"
        f"  {'rw_avg':>6}  {'mcp_saved_tok':>13}"
    )
    print(hdr)
    print("-" * len(hdr))
    for stem in sorted(groups):
        rows = groups[stem]
        n = len(rows)
        dins = [
            int((r.get("treatment") or {}).get("total_input", 0))
            - int((r.get("baseline") or {}).get("total_input", 0))
            for r in rows
        ]
        douts = [
            int((r.get("treatment") or {}).get("output_tokens", 0))
            - int((r.get("baseline") or {}).get("output_tokens", 0))
            for r in rows
        ]
        din_pcts = [
            _pct_raw(
                int((r.get("baseline") or {}).get("total_input", 0)),
                int((r.get("treatment") or {}).get("total_input", 0)),
            )
            for r in rows
        ]
        dout_pcts = [
            _pct_raw(
                int((r.get("baseline") or {}).get("output_tokens", 0)),
                int((r.get("treatment") or {}).get("output_tokens", 0)),
            )
            for r in rows
        ]
        rw = [int((r.get("rewrites") or {}).get("treatment", 0)) for r in rows]
        mcp = [
            int((r.get("mcp_compress") or {}).get("treatment_saved_chars", 0)) // 4
            for r in rows
        ]
        med_din = statistics.median(din_pcts)
        med_dout = statistics.median(dout_pcts)
        iqr_din = _iqr(din_pcts)
        iqr_dout = _iqr(dout_pcts)
        print(
            f"{stem[:24]:<24} {n:>3}  {med_din:>+7.1f}% {iqr_din:>8.1f}%  "
            f"{med_dout:>+8.1f}% {iqr_dout:>8.1f}%  {statistics.mean(rw):>6.1f}  {int(statistics.mean(mcp)):>13}"
        )
    return 0


def _pct_raw(a: int, b: int) -> float:
    if not a:
        return 0.0
    return (b - a) / a * 100


def _iqr(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    q = statistics.quantiles(xs, n=4)
    return q[2] - q[0]


if __name__ == "__main__":
    raise SystemExit(main())
