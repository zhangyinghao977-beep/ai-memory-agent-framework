# Reproducibility notes

[Back to The Abyss](../README.en.md) · [中文](REPRODUCIBILITY.zh.md)

These notes describe the checks and reproduction boundaries of the candidate copy. **They are not a record of a completed new reproduction.** Release preparation organized files and performed static checks; it did not run pytest, import the project, start training, or load historical weights. Historical results and new runs must retain separate identities.

## Environment and dependencies

In this guide, the root means the implementation directory `projects/the-abyss/implementation`, not the top level of the GitHub repository. From the repository top level, run this first, then use the remaining commands:

```sh
cd projects/the-abyss/implementation
```

The foundation storage and contract code uses the Python standard library, including sqlite3, json, and hashlib. Its test runner, pytest, is a third-party package. Neural experiments require the third-party package torch; T4 resource and subprocess paths also require psutil. Modules such as subprocess, pathlib, dataclasses, and pickle belong to the standard library and are not separate installation dependencies.

Use Python 3.11 or later and an isolated virtual environment. From the implementation root, install the foundation test dependencies with:

```sh
python -m pip install -e '.[test]'
```

For neural experiments and the complete test dependencies:

```sh
python -m pip install -e '.[experiments,test]'
```

The second group includes torch, numpy, psutil, and pytest, with installation versions specified by the dependency groups in `pyproject.toml`. The root `requirements-observed.txt` contains comments recording observed environment information; **it is neither an executable dependency lockfile nor a record of the historical experiment environments**. Record CPU/GPU use, thread counts, software versions, and random seeds for each new run. A historical environment does not establish bitwise reproducibility on arbitrary environments. These installation commands are steps for a reproducer to choose to execute; release preparation did not install dependencies.

The check that does not execute project code is:

```sh
python -B tools/check_static.py --report STATIC_CHECKS.json
```

It only scans AST, JSON, TOML, hashes, and paths and writes its own report. It does not replace import checks, pytest, or experiment execution. Refer to the actual generated file for its outcome.

This copy excludes the old `materials` and `toy` modules and their tests. It does not depend on external corpora, a tokenizer, or the 119M checkpoint. Some material tests in the original workspace skipped when files were absent; those skips are not counted as interface validation here.

## Choose the test scope first

The following **12 foundation contract-test files** are the first candidates for lightweight checks. Optionally add `test_t1.py` for synthetic task generation and rule baselines. They use no external data or neural training, but most create a SQLite database through `project/conftest.py` in pytest's temporary directory. Evaluation and integrity checks also write temporary plans and backups. **This candidate set was not run during release preparation and is not reported as passing.**

| File, under project/tests | Main checks |
|---|---|
| test_calls.py | Call inputs, candidates, feedback, and correction records |
| test_decisive_gate.py | Decisive-factor overlap and simple-shortcut gates |
| test_evaluation.py | Frozen plans, data overlap, baselines, and report conclusions |
| test_event_ast.py | AST structure, object bindings, evidence for conditions, and transitions |
| test_experience.py | Provenance, verification, occurrence records, and read-only access |
| test_formation.py | Package formation, local promotion, and concept relations |
| test_learning_integrity.py | Training receipts, logical forgetting, backups, and reference integrity |
| test_memory.py | Formation, imagination, revision, and recall |
| test_registry.py | Knowledge packages, versions, and local-correction contracts |
| test_relation_eval.py | Scales, direction, unknown values, and evaluation conversion |
| test_v017.py | Memory scope, stable references, and visibility at call time |
| test_valve.py | World boundaries, premise scope, and revocation |
| test_t1.py, optional | Synthetic tasks, splits, and rule baselines |

From the implementation root, this command explicitly selects those 13 files. It is a candidate check for a reproducer to choose to execute; **it was not run during release preparation**:

```sh
python -B -m pytest -q -p no:cacheprovider project/tests/test_calls.py project/tests/test_decisive_gate.py project/tests/test_evaluation.py project/tests/test_event_ast.py project/tests/test_experience.py project/tests/test_formation.py project/tests/test_learning_integrity.py project/tests/test_memory.py project/tests/test_registry.py project/tests/test_relation_eval.py project/tests/test_v017.py project/tests/test_valve.py project/tests/test_t1.py
```

Keep the relationship between `project/conftest.py`, `project/tests/_helpers.py`, and `project/empirical_core`. The tests' `_helpers` module is part of this repository, not a PyPI dependency. A changed layout or import mode requires a fresh importability check.

## What the other tests do

| Test group | Actual behavior |
|---|---|
| test_t1_models.py and test_t1_scale.py | Forward passes, gradient connectivity, and scale checks, including a model with roughly ten million parameters and a larger synthetic task; not zero-cost checks |
| test_t1_train.py, test_t2.py, and test_t3.py | Short training, local repair, and temporary weight-version I/O; a test name containing “read only” does not mean the entire test avoids training |
| test_t4.py | Temporary logs, SQLite databases, and weights; some tests learn; recovery checks start their own subprocesses, deliberately exit them, and start them again to verify recovery |
| test_t5.py through test_t10.py | Training and consistency checks on synthetic data; one T5 check runs 400 optimizer steps, and the other groups also contain real parameter updates |

T4 deliberately exits subprocesses created by the test, not existing experiments. It also depends on `experiments/t4_survival_20261103/live_t4.py`; copying `project/` alone is not sufficient for the complete suite. The release copy adds a `process_integration` marker and skips only that integration check if its runner is missing. Its subprocess defaults to one thread and at most one CPU from the currently allowed affinity set instead of fixed machine-specific CPU IDs. Thread counts and affinity are not a strict utilization cap. These static adaptations have not been validated by execution; see [core release-copy changes](CORE_CHANGES.md).

Some tests generate data and set torch thread counts during collection, so `--collect-only` is not merely a file listing. The older suite has no unified slow/integration classification. An unfiltered full-suite pytest invocation is not a substitute for selecting lightweight checks.

## Separate new runs from historical summaries

Use a new output directory for each run. Preserve its plan, source revision or hashes, environment, seeds, resource budget, splits, gates, receipts, and failures. Retain failure records. If a plan, metric, or analysis changes after observing results, record the change and a new identity rather than replacing the record with “the original plan passed.”

Evidence in `historical/` describes the original runs. Historical receipts, summaries, or source hashes do not establish reproduction by this copy. Portability edits also make the adapted sources bytewise different from their original frozen files; record a new source identity.

`historical/SOURCE_SNAPSHOT.json` records relative source paths and read-only SHA-256 hashes for copied files. It supports provenance, not a passing-test claim or a claim that adapted code is identical to the sources used by historical runs.

T10 historically completed 50/50 tasks; S2 failed, and generalization to unseen packages remains unresolved. Completed-task counts, engineering-contract checks, whether predictions held, and model scores are four distinct kinds of evidence. They must not be added together or used interchangeably. T8/T9/T10 retain human-designed rule-construction formulas, comparators, and windows. These controlled results do not establish complete autonomous knowledge formation or general continual learning.

Empiricist event chains represent objects, relations, conditions, and transitions. Hongchenxian work event chains concern execution and receipts. T4's hand-written FSM only borrows survival and recovery ideas from the latter; its execution is not an implementation claim for the Hongchenxian system.

## Experiment entry points and prerequisites

These are the adapted interfaces. **None of the runtime commands below was executed during release preparation.** Run them from the implementation root; paths are relative to that root. Each experiment directory has its own `PLAN.json`. The default new output name is `run_reproduction`; historical outputs must not be presented as a new run.

| Stage | Directory under experiments | Entry point | Prerequisite runs declared in PLAN |
|---|---|---|---|
| T1 | t1_run_20261101 | run_t1.py | None |
| Extended T1 | t1_run2_20261102 | run_t1.py | None |
| T2 | t2_repair_20261102 | run_t2.py | None |
| T3 | t3_mutual_stability_20261103 | run_t3.py | None |
| T4 | t4_survival_20261103 | run_t4.py | T3 |
| T5 | t5_content_choice_20261105 | run_t5.py | None |
| T6 | t6_lattice_parts_20261105 | run_t6.py | T5 |
| T7 | t7_noisy_lattice_20261106 | run_t7.py | T6 |
| T8 | t8_grown_lattice_20261106 | run_t8.py | T6, for post hoc comparison |
| T9 | t9_grown_rule_20261106 | run_t9.py | T8 |
| T10 | t10_relation_size_20261106 | run_t10.py | T8 and T9 |

Prerequisite paths are specified by `dependency_runs` in the plan and default to the corresponding experiment's `run_reproduction`. `dependency_run` checks the fresh-run marker, relative plan path and stage, frozen plan SHA256, and either early-stage completion records or later-stage gates and the expected number of JSON receipts. An existing directory alone is insufficient. These checks support artifact identity and completion-record consistency, not receipt correctness, weight completeness, or scientific comparability; the relevant readers must still validate required weights and results. Do not substitute empty directories for prerequisite experiments.

Portability changes target new runs made through this copy's entry points. Relocating an already generated run directory or checkpoint and resuming it has not been validated. Relative entry-point paths do not establish arbitrary portability of old artifacts.

T1, extended T1, T2, T3, and T4 take two positional arguments: the plan path and output path. One invocation starts the actual planned run, including training. T4 also injects subprocess failures. For example:

```sh
python -B experiments/t1_run_20261101/run_t1.py experiments/t1_run_20261101/PLAN.json experiments/t1_run_20261101/run_reproduction
```

Substitute the directory and script from the table for the other stages. T4's starting state depends on the T3 run and cannot omit its receipts and unit versions. T1–T4 report scripts take one output-directory argument, for example:

```sh
python -B experiments/t1_run_20261101/report_t1.py experiments/t1_run_20261101/run_reproduction
```

T3's `analyze_t3.py` requires exactly one run-directory argument. T4's `live_t4.py` retains its configuration-file and output-directory arguments for integration tests; it does not replace the main runner's plan and prerequisite checks. See [T1–T4 entry-point changes](EXPERIMENT_CHANGES_T1_T4.md) for adaptation details.

T5–T10 separate `gate` and `worker` modes. This example selects one worker, with index 0 and total count 1. The worker trains and writes receipts and model files:

```sh
python -B experiments/t5_content_choice_20261105/run_t5.py experiments/t5_content_choice_20261105/run_reproduction gate
python -B experiments/t5_content_choice_20261105/run_t5.py experiments/t5_content_choice_20261105/run_reproduction worker 0 1
python -B experiments/t5_content_choice_20261105/report_t5.py experiments/t5_content_choice_20261105/run_reproduction
```

T6–T9 use the same argument pattern with their directory and number substituted. T5–T9 gates do not train or load old weights, but they generate tasks and compute baselines. T8/T9 also construct experience vectors or relation tables, including operations such as SVD. They are not lightweight static checks.

**The T10 gate itself trains.** It runs 3000 steps for each of 2 task types × 2 models and compares them with existing T9 curve points. It requires the explicit `--allow-training` flag; this is not 3000 steps in total:

```sh
python -B experiments/t10_relation_size_20261106/run_t10.py experiments/t10_relation_size_20261106/run_reproduction gate --allow-training
python -B experiments/t10_relation_size_20261106/run_t10.py experiments/t10_relation_size_20261106/run_reproduction worker 0 1
python -B experiments/t10_relation_size_20261106/report_t10.py experiments/t10_relation_size_20261106/run_reproduction
```

T5–T10 reports use the run's frozen plan identity and reject a changed current PLAN or historical frozen files containing absolute paths. Reports require the corresponding receipts; generating a report cannot turn missing receipts into a completed run.

Post hoc analyses have separate output directories. `posthoc_tN.py` for T5, T6, T9, and T10 takes two positional arguments: the run directory and analysis output directory. T7 and T8 allow the second argument to be omitted, defaulting to `posthoc_reproduction` in the run directory's parent. For example:

```sh
python -B experiments/t9_grown_rule_20261106/posthoc_t9.py experiments/t9_grown_rule_20261106/run_reproduction experiments/t9_grown_rule_20261106/posthoc_reproduction
```

Post hoc analysis may load models from the new run and perform computation. It is not a static check, and its conclusions must be labeled as post hoc.

The adapted entry points default to `ABYSS_THREADS=1`. Optional `ABYSS_CPU_AFFINITY` accepts comma-separated CPU IDs that must belong to the current process's allowed set. Research output and dependency paths are constrained to the candidate root; T4 unit tests separately use their own temporary directories. Threads and affinity do not guarantee a strict utilization cap. Device settings, training budgets, and other resources must still be checked against the plan and execution environment.
