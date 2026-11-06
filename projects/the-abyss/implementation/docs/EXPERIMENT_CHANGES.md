# Experiment portability changes

This file describes edits to the independent release copy. The original local research workspace was not edited, imported, or executed. This copy is a reproduction candidate, not a completed independent reproduction.

## Configuration and evidence

- The new `experiments/*/PLAN.json` files retain research parameters from each original main configuration: synthetic task dimensions, model arms, seeds, training steps, optimizer settings, evaluation intervals and decision thresholds. Private authorization messages and original-machine scheduling were removed. Runtime defaults are one CPU thread and one worker, with no fixed CPU identifiers.
- These are **new reproduction configurations**. They are not the original frozen plans, and their creation after the historical results is not a new preregistration. `REPRODUCTION.md` replaces the private historical planning document in the T5–T10 source manifest.
- No old `FROZEN.json`, receipts, datasets, predictions, databases or weights were copied as runnable inputs. Historical summaries elsewhere in this repository are source-attributed records, not results produced by this release.
- New source manifests use paths relative to the release root and include the shared helper. Changing frozen source bytes still rejects resume. Moving the entire unchanged release tree no longer changes source-hash keys. This does not promise that existing generated runs or checkpoint internals can be moved: their migration has not been verified and internal artifact paths may still be bound to their original output location.
- T5–T10 reports and posthoc scripts use `load_run_plan`: the local plan path and SHA must agree with the new run's frozen plan. They do not follow an original-machine absolute `plan_path`. A changed plan cannot silently relabel a run.

## Runtime and paths

`experiments/_release_support.py` handles root-relative paths, explicit local dependencies, source hashing and cooperative runtime settings. It performs no experiment at import time.

- `ABYSS_THREADS` defaults to `1`. `ABYSS_CPU_AFFINITY` is optional and accepts comma-separated CPU identifiers. If requested, affinity must be a nonempty subset of the process's currently allowed CPUs. An unavailable affinity API produces a visible warning; it is not a requirement to train.
- Hard-coded Windows priority constants and CPU 8–16 bindings are removed from the portable runner setup. Thread counts, affinity and any retained duty-cycle scheduling are **not guarantees of a CPU/GPU utilization ceiling**.
- T5–T10 run/report paths and configured dependency paths are interpreted relative to the release root and must remain inside it. Dependency paths must be relative; the code does not search the original machine for missing inputs.
- Dependencies must have new reproduction FROZEN metadata, a relative local plan path with the expected stage name, and a matching frozen plan SHA. T1–T4 dependencies must have completed STATUS and PIPELINE_EXIT records. T5–T10 dependencies must have a passing gate, the expected number of receipts and valid JSON objects in those receipts. No weights are loaded by this check. Required individual weight files and detailed scientific compatibility are still checked by the consuming experiment, or fail on use; comparisons are not invented or skipped.
- Each runner is a program that can create files and perform substantial work. `report` and `posthoc` scripts also write reports. “No training” does not mean no computation or no writes.

## T5–T10 entry points

Run commands from the release root. The explicit `gate` action prepares a **fresh** output directory; `worker` resumes only an existing matching frozen run. Worker arguments are optional and default to `0 1` (one worker). The scripts do not launch additional workers automatically.

```text
python -B experiments/t5_content_choice_20261105/run_t5.py experiments/t5_content_choice_20261105/run_reproduction gate
python -B experiments/t5_content_choice_20261105/run_t5.py experiments/t5_content_choice_20261105/run_reproduction worker
python -B experiments/t5_content_choice_20261105/report_t5.py experiments/t5_content_choice_20261105/run_reproduction
```

Use the corresponding experiment directory and number for other stages. T5–T9 gates prepare synthetic tasks, baselines and, where applicable, experience-derived vectors/relations; they do not call model-training loops. This can still be significant computation, including SVD in the later stages.

**T10 gate trains models**: with the supplied configuration it runs two task types × two model types × 3,000 steps, then compares with configured T9 receipts. It requires an additional explicit flag:

```text
python -B experiments/t10_relation_size_20261106/run_t10.py experiments/t10_relation_size_20261106/run_reproduction gate --allow-training
```

Calling T10 `gate` without this flag errors before starting the gate. All `worker` commands are explicit training requests. A gate with recorded problems cannot be used to start a worker.

Posthoc scripts for T5, T6, T9 and T10 take `RUN OUTPUT` (both relative to the release root). T7 and T8 take `RUN [OUTPUT]`; the default output is a new `posthoc_reproduction` sibling directory. T9 posthoc loads its own run's models. T10 posthoc loads models from T8, T9 and T10. They perform inference/analysis and write results; no historical model files are bundled.

## Required experiment relationships

The supplied `dependency_runs` values point to the prerequisite experiment's `run_reproduction` directory. Change these values explicitly before freezing a new run if another local run is intended. Preserve the sibling layout of `project/` and `experiments/`.

| Stage | Required preceding artifacts |
|---|---|
| T3 | T2 runner/report source modules; it does not reuse T2 trained weights |
| T4 | T2 source modules and T3 two-way final receipts, snapshots and unit weights |
| T6 | T5 receipts for cross-experiment report/posthoc comparisons |
| T7 | T6 receipts for its clean-vector comparison |
| T8 | T6 receipts for posthoc comparison |
| T9 | T8 receipts for the m4 trajectory comparison, report and posthoc analysis |
| T10 | T9 receipts for the training gate; T8/T9 receipts for reporting; T8/T9 weights for posthoc analysis |

The T5–T10 CLI preflights every dependency run named in its plan, even when a particular action only needs a subset. The metadata/completion checks above are mandatory. They do not establish that two arbitrarily reconfigured runs are scientifically comparable or that all model files can be loaded. Run each predecessor with the supplied matching configuration, or explicitly audit any intentional changes.

T4 cannot reproduce the formal plan from source alone until the configured T3 starting weights have been produced. That requirement is retained, not replaced with random weights or a fabricated result. The T4 process-restart integration is an optional test path and deliberately starts/terminates its own child processes; it is not run by this preparation work.

## Scope of changes and validation limits

The intended changes concern orchestration, local file resolution, privacy, resource defaults and evidence handling. This task did not intentionally change synthetic task construction, model equations, losses, gradient updates, experimental arms, score formulas or decision thresholds. Path expressions inside training/report functions were changed where they read previous runs. T9's posthoc resource narrative was corrected to avoid assuming two threads after the default changed to one. T3's analysis now reports missing GPU telemetry explicitly for CPU runs instead of indexing a nonexistent GPU field or inventing a zero.

No training, project imports, model loads, experiment runs, pytest, CLI smoke tests or numerical comparisons were performed. Validation is limited to source review, JSON parsing and Python AST parsing. AST parsing checks syntax; it does not establish correct imports, compatible library versions, supported hardware, successful training, identical floating-point behavior or reproduced historical results. A different thread count or execution environment can change numerical results and wall time.

Historical performance claims remain limited to the original controlled synthetic tasks. Fixed FSM thresholds, symbolic identity constraints, configured repair ladders, generated worlds and posthoc analyses are not evidence of a general autonomous intelligence, autonomous coding or an implemented Hongchenxian system.

See `EXPERIMENT_CHANGES_T1_T4.md` for the earlier pipeline-specific adaptation details and remaining dependencies.
