#!/usr/bin/env python3
"""Grunt Phase 2: measure hypothetical compression savings on tool output.

PostToolUse observer. Does NOT mutate tool output (see NOTE). Computes what
compressed output would look like per-tool, logs before/after token counts to
.grunt/compression.jsonl so we can judge which tools are worth mutating later.

NOTE: Claude Code hook contract for mutating PostToolUse output varies. Safer
to measure first, then graduate to mutation once we know which compressors
don't break downstream tool-call chains.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path


ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
MULTI_BLANK_RE = re.compile(r"\n{3,}")
LS_LONG_RE = re.compile(
    r"^[\-dlrwxsStT]{10}\s+\d+\s+\S+\s+\S+\s+\d+\s+\w+\s+\d+\s+[\d:]+\s+(.+)$"
)

# Phrases safe to drop from agent prose — pure fluff, no semantic load.
FLUFF_PATTERNS = [
    # Preambles
    r"\bI (?:investigated|researched|looked (?:into|at)|searched|explored|analyzed|examined)\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    r"\bBased on (?:my |the )?(?:research|investigation|analysis|findings)\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    r"\bAfter (?:investigating|researching|looking|searching|analyzing|examining)\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    r"\b(?:Here(?:'s| is) (?:what I found|a summary|the result)|Let me (?:explain|walk you through))\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    # Closings
    r"\bLet me know if\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    r"\b(?:Hope|I hope) (?:this|that) helps\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    r"\bFeel free to\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    r"\b(?:Happy|I'?m happy) to\b[^.!?\n]*(?:[.!?]|\Z|(?=\n))[ \t]*",
    # Pleasantries
    r"\b(?:Sure|Certainly|Of course|Absolutely)[!,.]\s*",
    r"\bGreat question[!.]\s*",
]
FLUFF_RE = re.compile("(?:" + ")|(?:".join(FLUFF_PATTERNS) + ")", re.IGNORECASE)

# Individual filler words — drop if clearly adverbial (between whitespace).
FILLER_WORDS = ("just", "really", "basically", "actually", "simply", "essentially",
                "literally", "quite", "very", "perhaps", "maybe")
FILLER_RE = re.compile(
    r"\b(?:" + "|".join(FILLER_WORDS) + r")\s+", re.IGNORECASE
)


def est_tokens(s: str) -> int:
    return max(1, len(s) // 4)


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent.parent


def compress_text(s: str) -> str:
    s = ANSI_RE.sub("", s)
    s = MULTI_BLANK_RE.sub("\n\n", s)
    # Strip trailing whitespace per line.
    s = "\n".join(line.rstrip() for line in s.splitlines())
    return s.strip()


def compress_ls_long(s: str) -> str:
    """If looks like `ls -l`, drop metadata columns, keep filenames."""
    lines = s.splitlines()
    out = []
    hit = 0
    for line in lines:
        m = LS_LONG_RE.match(line)
        if m:
            out.append(m.group(1))
            hit += 1
        else:
            out.append(line)
    # only apply if we matched majority of non-empty lines
    non_empty = sum(1 for l in lines if l.strip())
    if non_empty and hit / non_empty > 0.6:
        return "\n".join(out)
    return s


def compress_bash_output(resp) -> str:
    if isinstance(resp, dict):
        stdout = resp.get("stdout") or resp.get("output") or ""
        stderr = resp.get("stderr") or ""
    else:
        stdout = str(resp or "")
        stderr = ""
    s = compress_text(stdout)
    s = compress_ls_long(s)
    if stderr.strip():
        s += "\n--stderr--\n" + compress_text(stderr)
    return s


def caveman_rewrite(s: str) -> str:
    """Drop fluff phrases + filler words. Safe — no sentence restructuring."""
    # Preserve code blocks by splitting on fences.
    parts = re.split(r"(```[\s\S]*?```|`[^`\n]+`)", s)
    for i, part in enumerate(parts):
        if part.startswith("`"):
            continue  # leave code / inline code alone
        part = FLUFF_RE.sub("", part)
        part = FILLER_RE.sub("", part)
        parts[i] = part
    out = "".join(parts)
    out = MULTI_BLANK_RE.sub("\n\n", out)
    return out.strip()


def extract_agent_text(resp) -> str:
    """Agent tool response shapes vary. Pull out the text content."""
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        for key in ("content", "output", "result", "text"):
            v = resp.get(key)
            if isinstance(v, str):
                return v
            if isinstance(v, list):
                chunks = []
                for item in v:
                    if isinstance(item, dict):
                        chunks.append(item.get("text") or item.get("content") or "")
                    else:
                        chunks.append(str(item))
                return "\n".join(c for c in chunks if c)
    return json.dumps(resp, ensure_ascii=False, separators=(",", ":"))


def compress_agent(resp) -> str:
    return caveman_rewrite(compress_text(extract_agent_text(resp)))


# Markdown noise patterns — safe to drop from fetched web content.
MD_HR_RE = re.compile(r"^(?:-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE)
MD_EMPTY_HEADER_RE = re.compile(r"^#{1,6}\s*$", re.MULTILINE)
MD_TRAILING_LINKS_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
HTML_ENTITY_RE = re.compile(r"&(?:nbsp|amp|lt|gt|quot|#\d+);")


def strip_markdown_noise(s: str) -> str:
    s = MD_HR_RE.sub("", s)
    s = MD_EMPTY_HEADER_RE.sub("", s)
    # Collapse `[text](url)` → `text` when url is long (url tokens wasted in agent
    # pipeline — orchestrator rarely clicks). Keep short urls.
    def _link(m):
        text, url = m.group(1), m.group(2)
        return text if len(url) > 40 else m.group(0)
    s = MD_TRAILING_LINKS_RE.sub(_link, s)
    # Cheap HTML entity decode.
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<")
    s = s.replace("&gt;", ">").replace("&quot;", '"')
    return s


def compress_read(resp) -> str:
    """Read output drives Edit tool — line numbers are load-bearing.

    Safe trims only: strip ANSI, strip trailing whitespace per line, collapse
    runs of 4+ blank lines. Never touch line number prefix or code content.
    """
    text = extract_agent_text(resp)
    text = ANSI_RE.sub("", text)
    # Strip trailing whitespace but keep line structure (line numbers + tabs intact).
    lines = [line.rstrip() for line in text.splitlines()]
    # "Blank" = line-number-only (rstrip ate the tab, leaving just digits).
    blank_re = re.compile(r"^\s*\d+$")
    out = []
    blank_run = 0
    for line in lines:
        if blank_re.match(line) or not line.strip():
            blank_run += 1
            if blank_run <= 2:
                out.append(line)
        else:
            blank_run = 0
            out.append(line)
    return "\n".join(out)


def compress_webfetch(resp) -> str:
    """WebFetch returns model-generated prose about a URL. Prose is compressible."""
    text = extract_agent_text(resp)  # same shape logic works
    text = compress_text(text)
    text = strip_markdown_noise(text)
    text = caveman_rewrite(text)
    # Second pass — caveman_rewrite may empty out headers like `# Based on my research`.
    text = strip_markdown_noise(text)
    text = MULTI_BLANK_RE.sub("\n\n", text).strip()
    return text


def compress_generic(resp) -> str:
    if isinstance(resp, str):
        return compress_text(resp)
    try:
        return json.dumps(resp, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(resp)


def compress(tool: str, resp) -> str:
    if tool == "Bash":
        return compress_bash_output(resp)
    if tool == "Agent" or tool == "Task":
        return compress_agent(resp)
    if tool == "WebFetch":
        return compress_webfetch(resp)
    if tool == "Read":
        return compress_read(resp)
    return compress_generic(resp)


def main() -> int:
    raw = sys.stdin.read()
    try:
        evt = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(json.dumps({"continue": True}))
        return 0

    if evt.get("hook_event_name") != "PostToolUse":
        print(json.dumps({"continue": True}))
        return 0

    tool = evt.get("tool_name", "")
    resp = evt.get("tool_response")
    if resp is None:
        print(json.dumps({"continue": True}))
        return 0

    original = resp if isinstance(resp, str) else json.dumps(
        resp, ensure_ascii=False, separators=(",", ":")
    )
    compressed = compress(tool, resp)

    rec = {
        "ts": time.time(),
        "session": evt.get("session_id", ""),
        "tool": tool,
        "orig_tok": est_tokens(original),
        "comp_tok": est_tokens(compressed),
        "saved_tok": est_tokens(original) - est_tokens(compressed),
    }
    out_dir = project_root() / ".grunt"
    out_dir.mkdir(exist_ok=True)
    with (out_dir / "compression.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(json.dumps({"continue": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
