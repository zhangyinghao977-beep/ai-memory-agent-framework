# T10: reproduction configuration

This is a new, sanitized reproduction configuration, not the historical frozen plan. No historical results, receipts, weights, or authorization messages are included.

The task, model-arm, seed, step, optimizer and decision-threshold parameters in PLAN.json are retained from the original main configuration. Resource settings default to one CPU thread and one worker. These settings do not enforce a hardware utilization ceiling.

Paths in dependency_runs are relative to the release root. Generate those runs first; missing comparisons are errors, not skipped results. Use a fresh run directory and generate new FROZEN metadata. See docs/EXPERIMENT_CHANGES.md for limitations.

T10 gate performs training and requires an explicit --allow-training flag.
