For each Python file under `agent-caveman/hooks/` (excluding `__pycache__`),
spawn one `grunt-explorer` subagent (via the Agent/Task tool with
`subagent_type: grunt-explorer`) to return a one-sentence description of
what that file does. Run the subagents serially.

Output a single bulleted list, one bullet per file:

- `path`: one-sentence purpose.

No narrative. No preamble. No closing summary.
