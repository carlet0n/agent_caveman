<!--
NOOP CONTROL TASK — NOT AN A/B FOR THE PLUGIN.

This task invokes only Read/Glob/Grep from the lead agent. None of the
plugin's hooks target those tools (rewriter matches WebFetch|Agent|Task;
MCP compressor matches mcp__github__.*). So treatment and baseline run
byte-identical code paths.

Use this only to measure the noise floor of `compare.py`'s deltas for a
given N. A meaningful-looking median here is evidence you need more reps,
not evidence the plugin did anything.
-->

Survey the agent-caveman repository at the allowed directory. Identify:

1. Every file under `agent-caveman/hooks/` and its one-line purpose.
2. The list of subagents defined under `agent-caveman/agents/`.
3. Which environment variables can disable behavior.

Respond with three short sections: HOOKS, AGENTS, ENV. No narrative, no preamble.
