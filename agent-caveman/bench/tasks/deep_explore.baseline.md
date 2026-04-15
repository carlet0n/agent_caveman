Spawn exactly one `general-purpose` subagent (via the Agent/Task tool with
`subagent_type: general-purpose`). The subagent must answer the following
question by doing its own exploration — do not answer it yourself.

Inside the subagent, perform a thorough audit of
`agent-caveman/` and return:

1. Every Python file's path and a one-sentence purpose.
2. Every JSON file under the repo (paths only).
3. Every markdown file under `agent-caveman/skills/` and
   `agent-caveman/commands/` (paths only).
4. Every occurrence of `os.environ.get(` in any Python file — report
   `file:line` and the env var name.
5. Every hook registration in `hooks/hooks.json` — matcher, event,
   command filename.

The subagent should use Read, Grep, and Glob liberally to verify each
answer before reporting. Output as five numbered sections. No narrative.
