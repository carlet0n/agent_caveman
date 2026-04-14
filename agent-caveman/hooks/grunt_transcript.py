#!/usr/bin/env python3
"""Read authoritative token usage from Claude Code session transcripts.

Claude Code writes assistant-turn transcripts to
~/.claude/projects/<munged-cwd>/<session>.jsonl, with each assistant message
carrying the real `usage` object returned by the API (input_tokens,
output_tokens, cache_read_input_tokens, cache_creation_input_tokens).

Char/4 estimates in .grunt/metrics.jsonl drift 10-30% from real token counts
and never see cache reads, system prompt, or tool schemas. Totals from the
transcript are the billable truth.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def _munge(path: Path) -> str:
    s = str(path.resolve())
    out = []
    for ch in s:
        out.append("-" if ch in ("/", "_", ".") else ch)
    return "".join(out)


def transcript_dir(project: Path) -> Path:
    return Path.home() / ".claude" / "projects" / _munge(project)


def iter_assistant_usage(tdir: Path, session: str | None = None):
    """Yield (session_id, timestamp, usage_dict) for each assistant message."""
    if not tdir.exists():
        return
    files = sorted(tdir.glob("*.jsonl"))
    for f in files:
        sid = f.stem
        if session and sid != session:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("message") or {}
            u = msg.get("usage")
            if not u or msg.get("role") != "assistant":
                continue
            yield sid, d.get("timestamp", ""), u


def aggregate(tdir: Path, session: str | None = None) -> dict:
    totals = {
        "turns": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "sessions": set(),
    }
    for sid, _ts, u in iter_assistant_usage(tdir, session):
        totals["turns"] += 1
        totals["sessions"].add(sid)
        for k in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
        ):
            totals[k] += int(u.get(k) or 0)
    totals["sessions"] = sorted(totals["sessions"])
    totals["total_input"] = (
        totals["input_tokens"]
        + totals["cache_read_input_tokens"]
        + totals["cache_creation_input_tokens"]
    )
    return totals


def format_report(t: dict) -> str:
    if t["turns"] == 0:
        return "authoritative usage: no transcript turns found"
    lines = [
        f"authoritative usage (from transcript, {t['turns']} assistant turns, "
        f"{len(t['sessions'])} session(s)):",
        f"  input (fresh)          {t['input_tokens']:>12}",
        f"  input (cache read)     {t['cache_read_input_tokens']:>12}",
        f"  input (cache create)   {t['cache_creation_input_tokens']:>12}",
        f"  input total            {t['total_input']:>12}",
        f"  output                 {t['output_tokens']:>12}",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default=os.environ.get("CLAUDE_PROJECT_DIR") or ".")
    ap.add_argument("--session")
    args = ap.parse_args()
    tdir = transcript_dir(Path(args.project))
    print(f"transcript dir: {tdir}")
    print(format_report(aggregate(tdir, args.session)))
