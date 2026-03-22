---
name: Post Analysis Package
description: Package guidance for drill-down, historical comparison, and selective refetch tasks built on top of the post-analysis executor.
---

# Runtime Guidance

- Use this package only after the workflow already has analysis results, fetched answers, or snapshots to work from.
- Decide whether the user wants deeper interpretation, cross-run comparison, or a targeted refetch.
- Reuse the existing evidence first; only escalate to selective refetch when the missing piece cannot be answered from current materials.

# Output Expectations

- Keep responses task-shaped: compare when asked to compare, zoom in when asked to drill down, and confirm the narrowed scope when refetching.
- Preserve continuity with prior findings instead of restating the full report.
- Make the next action obvious when evidence is incomplete.
