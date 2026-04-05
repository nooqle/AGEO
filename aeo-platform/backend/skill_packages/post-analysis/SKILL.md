---
name: Post Analysis Package
description: Package guidance for drill-down and historical comparison tasks built on top of the post-analysis executor.
---

# Runtime Guidance

- Use this package only after the workflow already has analysis results, fetched answers, or snapshots to work from.
- Decide whether the user wants deeper interpretation or cross-run comparison.
- Reuse the existing evidence first; if the missing piece requires fresh data, hand the need back to the orchestrator so it can route to answer_fetch.

# Output Expectations

- Keep responses task-shaped: compare when asked to compare, zoom in when asked to drill down.
- Preserve continuity with prior findings instead of restating the full report.
- Make the next action obvious when evidence is incomplete, and explicitly say when new fetching would be more appropriate than more analysis.
