# 深渊 / The Abyss

- **Logic is the path that makes knowledge reachable.**
  逻辑是知识的可达路径。

[中文](README.md) · [Reproducibility notes](docs/REPRODUCIBILITY.en.md)

The Abyss is a research approach to AI memory, knowledge organization, and local learning. This candidate contains part of its implementation and controlled experiments: retaining experiences, separating them from formed memories, registering versioned knowledge packages, and studying how event chains invoke and revise local computational units.

**This is a research preview. The overall design is not fully implemented.** It is not a ready-to-use general agent or a plugin already shown to provide continual learning for arbitrary LLMs. Implemented code, experimental observations, and architectural hypotheses are described separately so that their evidence can be checked.

This is an independently prepared source-code research preview. **Its installation, test, and training workflows have not been validated by execution in this copy.** Preparation used static checks only; see [STATIC_CHECKS.json](STATIC_CHECKS.json). The public code license remains undecided; see [license status](LICENSE-STATUS.md). Public readability does not grant an open-source license.

| Layer | What this preview contains | What it supports |
|---|---|---|
| Implemented code | SQLite experience and memory storage, provenance and version records, knowledge-package registration, an event-chain AST, working caches and boundary checks, and local-correction records | These structures and interfaces exist; current test results require a new recorded run in the chosen environment |
| Controlled synthetic experiments | T1–T10 task generators, local KA/EA/CA computation, staged training, repair, a survival experiment with a fixed FSM, and lattice comparisons | Observations under specified generators, seeds, budgets, and human-designed structure; not automatic generalization to natural language or open environments |
| Working hypotheses | More complete knowledge formation from experience, broader generalization, long-term continual learning, and continuity of an agent | Research directions; the existing local results do not establish the complete design |

In these experiments, KA, EA, and CA perform local roles such as computation within a package, selection of an event within a chain, and selection between chains. These are specific experimental units, not universal definitions of attention mechanisms.

Two kinds of event chain must remain distinct. **Empiricist event chains** represent objects, relations, conditions, and transitions used for learning and reasoning. **Hongchenxian work event chains** record tool calls, execution receipts, artifacts, and recovery. They are not interchangeable. T4 borrows ideas about survival and recovery; its FSM is written by hand. It does not establish an implementation of Hongchenxian or an autonomous coding system.

The historical work has progressed beyond the early “not trained yet” stage. T10 records **50/50 completed tasks**, but completion does not mean that every prediction held: **S2 failed, and generalization to unseen packages remains unresolved**. T8/T9/T10 derive vectors or relation tables from synthetic event chains, while their construction formulas, comparators, windows, and other structure remain partly designed by humans. Historical summaries and new reproduction records must stay separate. No training or pytest run was performed while preparing this release, and these scores have not been independently reproduced in this copy.

Start here:

- [project/empirical_core](project/empirical_core/): the foundation and T1–T10 modules.
- [project/tests](project/tests/): contract, synthetic-task, training, and recovery tests with different execution costs.
- [experiments](experiments/): experiment runners, report generators, and post hoc analysis scripts.
- [historical](historical/): selected historical evidence and summaries, not new runs of this copy.
- [Reproducibility notes](docs/REPRODUCIBILITY.en.md): dependencies, candidate lightweight checks, training, and subprocess behavior.
- [Data sources](docs/DATA_SOURCES.en.md), [notices](NOTICES.md), and [license status](LICENSE-STATUS.md): provenance and reuse boundaries.

Read the implementation and reproduction notes before choosing what to run. The 12 foundation contract-test files plus `test_t1.py` are candidates for checks without external data or neural training. They still write their own temporary files or databases and were not run during release preparation. Other tests can train models. T4 also starts its own subprocesses, deliberately exits them at selected fault points, and checks recovery.

The preview excludes external corpora, pretrained weights, runtime databases, private collaboration records, the old material-integration module, and the retired toy experiment. Claims are limited to the code and evidence actually available.
