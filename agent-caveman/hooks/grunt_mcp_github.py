#!/usr/bin/env python3
"""PostToolUse hook: trim GitHub MCP responses before the model reads them.

GitHub REST payloads (and therefore GitHub MCP tool responses) bundle dozens of
URL fields, node IDs, avatar blobs, and reaction objects per item. For most
agent tasks only a handful of fields are actually useful. This hook walks the
parsed JSON and drops the known-bloat fields, replacing verbose `user` objects
with `{login}` and compressing `labels`/`assignees` to name arrays.

Matches tools named `mcp__github__*` via hook matcher. MCP responses are the
only tool outputs Claude Code lets us mutate post-execution, via
`updatedMCPToolOutput`.

Every compression is logged to .grunt/mcp_compress.jsonl (tool, before/after
char count) so users can audit the savings. Disable with GRUNT_MCP_COMPRESS=off.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


URL_SUFFIXES = (
    "_url",
)
DROP_KEYS = {
    "node_id",
    "gravatar_id",
    "avatar_url",
    "author_association",
    "performed_via_github_app",
    "active_lock_reason",
    "locked",
    "state_reason",
    "timeline_url",
    "reactions",
    "repository_url",
    "url",
}
KEEP_URL_KEYS = {"html_url"}


def project_root() -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path(__file__).resolve().parent.parent.parent


def _compact_user(u):
    if isinstance(u, dict) and "login" in u:
        return {"login": u["login"]}
    return u


def trim(obj):
    if isinstance(obj, list):
        return [trim(x) for x in obj]
    if not isinstance(obj, dict):
        return obj
    out: dict = {}
    for k, v in obj.items():
        if k in DROP_KEYS:
            continue
        if k.endswith(URL_SUFFIXES) and k not in KEEP_URL_KEYS:
            continue
        if k in ("user", "assignee", "author", "closed_by", "merged_by"):
            out[k] = _compact_user(v)
        elif k == "assignees" and isinstance(v, list):
            out[k] = [_compact_user(x) for x in v]
        elif k == "labels" and isinstance(v, list):
            out[k] = [x.get("name", x) if isinstance(x, dict) else x for x in v]
        elif k == "milestone" and isinstance(v, dict):
            out[k] = {"title": v.get("title")} if v.get("title") else None
        elif k == "pull_request" and isinstance(v, dict):
            out[k] = {"html_url": v.get("html_url")}
        else:
            out[k] = trim(v)
    return out


def _try_parse(text: str):
    try:
        return json.loads(text), True
    except (json.JSONDecodeError, TypeError):
        return None, False


def compress_response(resp):
    """Return (new_response, before_chars, after_chars) or (resp, 0, 0) on no-op."""
    if isinstance(resp, str):
        parsed, ok = _try_parse(resp)
        if not ok:
            return resp, 0, 0
        trimmed = trim(parsed)
        new = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"))
        return new, len(resp), len(new)

    if isinstance(resp, dict) and isinstance(resp.get("content"), list):
        before = after = 0
        new_content = []
        changed = False
        for item in resp["content"]:
            if isinstance(item, dict) and item.get("type") == "text":
                txt = item.get("text", "")
                parsed, ok = _try_parse(txt)
                if ok:
                    new_txt = json.dumps(
                        trim(parsed), ensure_ascii=False, separators=(",", ":")
                    )
                    before += len(txt)
                    after += len(new_txt)
                    changed = True
                    new_content.append({**item, "text": new_txt})
                    continue
            new_content.append(item)
        if changed:
            return {**resp, "content": new_content}, before, after
    return resp, 0, 0


def log(session: str, tool: str, before: int, after: int) -> None:
    out_dir = project_root() / ".grunt"
    out_dir.mkdir(exist_ok=True)
    rec = {
        "ts": time.time(),
        "session": session,
        "tool": tool,
        "before_chars": before,
        "after_chars": after,
        "saved_chars": before - after,
    }
    with (out_dir / "mcp_compress.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    if os.environ.get("GRUNT_MCP_COMPRESS", "").lower() in ("off", "0", "false", "no"):
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    raw = sys.stdin.read()
    try:
        evt = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    if evt.get("hook_event_name") != "PostToolUse":
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    tool = evt.get("tool_name", "")
    if not tool.startswith("mcp__github__"):
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    resp = evt.get("tool_response")
    new_resp, before, after = compress_response(resp)
    if before == 0 or after >= before:
        sys.stdout.write(json.dumps({"continue": True}))
        return 0

    log(evt.get("session_id", ""), tool, before, after)

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "updatedMCPToolOutput": new_resp,
        }
    }
    sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
