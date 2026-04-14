---
description: Show agent-caveman token metrics for this project (tool call counts, compression savings, subagent costs)
argument-hint: "[--session <id>]"
---

Run the agent-caveman metrics report and show the user the results. The report lives inside the plugin.

!`python3 "${CLAUDE_PLUGIN_ROOT}/hooks/grunt_report.py" $ARGUMENTS`

After the report runs, briefly interpret the numbers for the user:

1. Call out which tool is consuming the most tokens
2. Note the compression-potential percentage per tool
3. If Agent/subagent calls exist, compare their avg return cost to 350 tokens (our baseline for verbose `general-purpose`) — lower is better
4. If WebFetch averages above 1000 tokens per call, suggest the `grunt-orchestrator` skill for tighter prompts

Keep the interpretation to 3-4 lines. Don't restate the numbers — just highlight what matters.
