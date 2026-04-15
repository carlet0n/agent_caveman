#!/usr/bin/env python3
"""Side-by-side token comparison of two bench runs.

Each argument is a project directory used as CLAUDE_PROJECT_DIR for one run.
Reads the Claude Code session transcript for each and prints:

  - authoritative usage (input/cache/output) per run and delta
  - hook-observed per-tool breakdown per run and delta
  - rewrite counts / MCP compression savings per run

Run bench/run.sh to produce the two project dirs, then pass them here.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from collections import defaultdict
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent.parent / "hooks"
sys.path.insert(0, str(HOOKS_DIR))
import grunt_transcript  # noqa: E402


def _load_metrics(project: Path) -> list[dict]:
    p = project / ".grunt" / "metrics.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def _tool_totals(rows: list[dict]) -> dict[str, dict[str, int]]:
    t: dict[str, dict[str, int]] = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0})
    for r in rows:
        tool = r.get("tool") or "?"
        if r.get("event") == "PreToolUse":
            t[tool]["calls"] += 1
            t[tool]["in"] += r.get("in_tok", 0)
        elif r.get("event") == "PostToolUse":
            t[tool]["out"] += r.get("out_tok", 0)
    return t


def _count_jsonl(project: Path, name: str) -> tuple[int, int]:
    p = project / ".grunt" / name
    if not p.exists():
        return 0, 0
    n = 0
    saved = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        n += 1
        saved += int(r.get("saved_chars") or 0)
    return n, saved


def _fmt_delta(a: int, b: int) -> str:
    d = b - a
    pct = (d / a * 100) if a else 0.0
    sign = "+" if d >= 0 else ""
    return f"{sign}{d:>8}  ({sign}{pct:6.1f}%)"


def _transcript_totals(project: Path) -> dict:
    return grunt_transcript.aggregate(grunt_transcript.transcript_dir(project))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--treatment", required=True, type=Path)
    ap.add_argument(
        "--history",
        type=Path,
        default=Path(__file__).resolve().parent / "history.jsonl",
        help="append one JSONL summary row here (default: bench/history.jsonl). Pass empty string to skip.",
    )
    ap.add_argument("--label", default=None, help="label for history row (default: run-dir name)")
    args = ap.parse_args()

    a = _transcript_totals(args.baseline)
    b = _transcript_totals(args.treatment)
    print("=== authoritative usage (from session transcript) ===")
    print(f"{'metric':<28}{'baseline':>12}{'treatment':>12}   delta")
    for key in (
        "turns",
        "input_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "total_input",
        "output_tokens",
    ):
        av, bv = int(a.get(key, 0)), int(b.get(key, 0))
        print(f"{key:<28}{av:>12}{bv:>12}   {_fmt_delta(av, bv)}")

    ta = _tool_totals(_load_metrics(args.baseline))
    tb = _tool_totals(_load_metrics(args.treatment))
    tools = sorted(
        set(ta) | set(tb),
        key=lambda t: -(ta.get(t, {}).get("out", 0) + tb.get(t, {}).get("out", 0)),
    )
    if tools:
        print("\n=== hook-observed per-tool out_tok (char/4) ===")
        print(f"{'tool':<20}{'base':>10}{'treat':>10}   delta")
        for t in tools:
            av = ta.get(t, {}).get("out", 0)
            bv = tb.get(t, {}).get("out", 0)
            print(f"{t:<20}{av:>10}{bv:>10}   {_fmt_delta(av, bv)}")

    print("\n=== plugin effects ===")
    rwa, _ = _count_jsonl(args.baseline, "rewrites.jsonl")
    rwb, _ = _count_jsonl(args.treatment, "rewrites.jsonl")
    mca, msaveda = _count_jsonl(args.baseline, "mcp_compress.jsonl")
    mcb, msavedb = _count_jsonl(args.treatment, "mcp_compress.jsonl")
    print(f"prompt rewrites applied   base={rwa:<6} treat={rwb}")
    print(
        f"mcp compress calls/chars  base={mca}/{msaveda}  treat={mcb}/{msavedb}"
        f"  (≈ {msavedb // 4} tok saved in treatment)"
    )

    if str(args.history):
        run_dir = args.baseline.parent if args.baseline.parent == args.treatment.parent else None
        label = args.label or (run_dir.name if run_dir else args.baseline.name)
        row = {
            "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
            "label": label,
            "run_dir": str(run_dir) if run_dir else None,
            "baseline": {k: int(a.get(k, 0)) for k in (
                "turns", "input_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "total_input", "output_tokens")},
            "treatment": {k: int(b.get(k, 0)) for k in (
                "turns", "input_tokens", "cache_read_input_tokens",
                "cache_creation_input_tokens", "total_input", "output_tokens")},
            "rewrites": {"baseline": rwa, "treatment": rwb},
            "mcp_compress": {
                "baseline_calls": mca, "baseline_saved_chars": msaveda,
                "treatment_calls": mcb, "treatment_saved_chars": msavedb,
            },
        }
        args.history.parent.mkdir(parents=True, exist_ok=True)
        with args.history.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row) + "\n")
        print(f"\nappended history row → {args.history}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
