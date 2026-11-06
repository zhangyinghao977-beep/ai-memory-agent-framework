# T1–T4 portable reproduction entry points

This release contains new reproduction configurations. They are not the original frozen plans and have not been executed. Historical results do not certify these modified entry points. Only Python AST parsing and static inspection were performed while preparing them; no project module, test, training run, or model evaluation was executed.

## What changed

- Main `PLAN.json` files retain the historical task, model, seeds, training, comparison, repair, and evaluation parameters. Personal conversation, authorization quotes, old process IDs, machine paths, past run status, and scheduling notes were excluded. Each plan declares `reproduction_config: true` and identifies its historical experiment.
- Runtime defaults are CPU, one thread, no CPU affinity, and no priority change. `ABYSS_THREADS` can override the thread count. Optional `ABYSS_CPU_AFFINITY` is checked against CPUs currently available to the process; unsupported platforms continue without affinity. The default free-memory threshold is 1 GiB and its wait budget is one minute. The prior elapsed-time and RSS stop thresholds remain configurable.
- Runtime settings are cooperative controls, not guarantees of a percentage of CPU or GPU utilization. Optional GPU pauses and allocator settings remain available, but the supplied configurations use CPU. Device, thread count, timings, and numerical behavior can differ from the historical machine. A large historical workload can reach the retained time limit under the new single-thread default.
- Main runner arguments resolve inside this release root. New `FROZEN.json` records use root-relative plan/source paths and include the shared release helper and effective runtime settings. Resume still requires identical plan/source bytes and effective thread/affinity settings. Use a fresh output directory instead of inserting historical `FROZEN.json` or receipts.
- Reports reject absolute plan references and paths outside this release. They also check the current plan SHA against the new run metadata. They no longer follow a historical `FROZEN.plan_path` to the original machine. Newly generated reports identify themselves as reproduction reports. T1 resource descriptions no longer claim the original CPU/GPU configuration.
- T3 still imports the T2 runner/report utilities using their sibling directories. Its frozen source list now includes `report_t2.py` as well as `run_t2.py`. T4 also retains these explicit code dependencies. Keep `project/`, `experiments/_release_support.py`, and the dated experiment directories together.
- The second T1 run no longer probes or waits for an old process. It is a separate manually invoked experiment.
- `analyze_t3.py` requires an explicit run directory and validates its local plan/source references. Its stopping-rule comparisons remain post-hoc analyses, not pre-registered findings or actual early stopping.

## Entry points

Run commands from this release root. These commands are examples for a future deliberate reproduction: the main runners perform training, and T4 also intentionally terminates its own child processes at selected failure-injection points.

```text
python -B experiments/t1_run_20261101/run_t1.py experiments/t1_run_20261101/PLAN.json experiments/t1_run_20261101/run_reproduction
python -B experiments/t1_run2_20261102/run_t1.py experiments/t1_run2_20261102/PLAN.json experiments/t1_run2_20261102/run_reproduction
python -B experiments/t2_repair_20261102/run_t2.py experiments/t2_repair_20261102/PLAN.json experiments/t2_repair_20261102/run_reproduction
python -B experiments/t3_mutual_stability_20261103/run_t3.py experiments/t3_mutual_stability_20261103/PLAN.json experiments/t3_mutual_stability_20261103/run_reproduction
```

T1 first/second and T2 do not need an older experiment's weights. T3 uses T2's code but trains its own starting units. All use the included synthetic task generators.

T4's supplied main plan **requires a completed T3 reproduction**, including `receipts/two_way-s{seed}.json` and the adopted unit versions under `work/s{seed}/two_way/`. Its explicit configuration is:

```json
{
  "start": {"dependency": "t3"},
  "dependency_runs": {
    "t3": "experiments/t3_mutual_stability_20261103/run_reproduction"
  }
}
```

Dependency paths must remain relative to this release root. Missing runs, receipts, data identity, or unit files are reported as errors; there is no fallback to historical results or original-machine weights. The T4 gate still checks that its synthetic world matches the T3 starting data.

After T3 completes:

```text
python -B experiments/t4_survival_20261103/run_t4.py experiments/t4_survival_20261103/PLAN.json experiments/t4_survival_20261103/run_reproduction
python -B experiments/t3_mutual_stability_20261103/analyze_t3.py experiments/t3_mutual_stability_20261103/run_reproduction
```

Report scripts accept a run directory relative to this release root, for example:

```text
python -B experiments/t4_survival_20261103/report_t4.py experiments/t4_survival_20261103/run_reproduction
```

`live_t4.py <CONF.json> <output-directory>` retains its existing low-level CLI so isolated temporary-directory recovery tests remain possible. When a starting-unit root is supplied, it must resolve inside this release; generated configurations record that root relatively. The low-level entry point performs a life simulation and may train. It is not a read-only viewer.

## Evidence boundaries

Preserved limits include synthetic tasks, fixed hyperparameters, hand-written identity constraints, and post-hoc analysis distinctions. T3's single-direction indirect-package failure is partly guaranteed by task construction. T4's fixed FSM/resource thresholds are scaffolding, and its recovery checks cover selected interruption sites only. T4 borrows design ideas from Hongchenxian; these experiments are not evidence that Hongchenxian or autonomous coding is implemented.

Generated runtime logs may contain new local environment information. Treat them as local experiment outputs and review them separately before public distribution. The release has not copied old frozen metadata, full receipts, or learned weights into these new run locations.
