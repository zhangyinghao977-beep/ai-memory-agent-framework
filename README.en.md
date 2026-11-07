# The Abyss and Hongchenxian / 深渊与红尘仙

English · [简体中文](README.md)

**Logic, memory and FSM:** [New design-principles and evaluation note (Chinese)](docs/MEMORY_LOGIC_FSM_PRINCIPLES.md) separates original memory text from knowledge relations, explains the agent slice and local attention, and distinguishes design, inspected implementation and open validation questions.

**Evaluation correction:** [Acknowledging errors in evaluation perspective and inference, and recording two project evaluation directions](projects/the-abyss/EVALUATION_CORRECTION.en.md): becoming more like a human; correspondence with and combination of Turing’s and von Neumann’s ideas. Historical results and frozen records are retained.

**Latest G1 execution:** [Complete ten-seed results](projects/the-abyss/research/g1-granularity-20261107/followup-20261107-execution3/README.en.md): 10/10 seeds and 140/140 units completed. The earlier two-seed resource-stop snapshot is retained.

**CA naming confirmed:** PA (Page Attention) is the former name of CA (Chain Attention). [Use-side addressing follows CA → EA → KA](docs/ARCHITECTURE_FLOWS.en.md#use-addressing), separately from learning loops.

**Current concepts and workflows (2026-11-07):** [Learning event chain EA, cached-experience integration, and active memory search](docs/ARCHITECTURE_FLOWS.en.md). Local attention is registered as a phase-two design, not a completed implementation. Active search now takes priority over the earlier passive-first plan, which is retained as history.

**Complete glossary:** [Bilingual terminology and event-chain boundaries](docs/GLOSSARY.en.md), including the latest three correction rounds, implementation mappings and open questions.

**Earlier evidence snapshot:** [2026-11-07 research-record update](projects/the-abyss/evidence/2026-11-07/README.en.md) covers v18.1, T11, subsequent-stage status, and the G1 granularity pilot. G1 stopped at its resource gate after 2/10 seeds; the earlier Abyss implementation copy's static-validation scope remains unchanged.

One repository, two separate research projects. This is an **unfinished AI approach to memory, learning, and agent collaboration**: adding persistent records, knowledge organization, and work continuity that a base LLM does not itself provide, while studying local learning. **This is a bilingual research preview, not a fully implemented or validated system. The project license has not been selected; public availability does not grant an open-source license.**

## Two entry points

### [The Abyss / 深渊](projects/the-abyss/README.en.md)

**Opening: a tribute to Newton**

> Next, I will show you the basic rules by which logic operates.
>
> What is an apple?

This opening and apple question form the project's twofold tribute to Isaac Newton. Neither is a quotation from him. They introduce the research proposition below; the “basic rules” remain to be articulated and tested.

1. **Logic is the path that makes knowledge reachable.**
   逻辑是知识的可达路径。

This is a theoretical proposition of the project, not a conclusion established by experiments. The project examines how experience forms reusable knowledge, how knowledge is composed and unfolded, and how new experience leads to revision. Its entry point provides the design, sources, and evidence boundaries in Chinese and English.

This integration retains the theory documents and adds selected original research sources with release adaptations under [implementation](projects/the-abyss/implementation/README.en.md): 65 core Python files, 25 `test_*.py` files, 31 experiment Python files including the shared helper, and 11 plans. They cover memory and provenance records, knowledge packages, an event-chain AST, and T1–T10 controlled synthetic experiments. This is not a distribution of the entire local workspace.

Code existence, historical execution, and validation of this copy are distinct states. The Abyss integration received static checks only: no dependency installation, project imports, pytest execution, training, or independent reproduction of historical scores. T10 historically has 50/50 receipts, but **S2 failed and generalization to unseen packages remains unresolved**. Complete receipts are not a “50/50 experimental success rate.” See the [evidence boundaries](projects/the-abyss/EVIDENCE.en.md) and [historical summary](projects/the-abyss/implementation/historical/RESULTS.en.md).

### [Hongchenxian / 红尘仙](projects/hongchenxian/README.en.md)

Research on collaboration among black-box agents: persistent identity, paragraph-indexed memory, frozen shared snapshots, per-step call accounting, lifecycle decisions, and source-verified recovery. Its existing offline synthetic engineering path uses Node built-ins. This integration preserves that source and its findings.

The empiricist learning event chain (EA) and work event chain cover formation and use respectively, like the learning and work forests. Hongchenxian's work-event chain corresponds to the work side and covers records, calls, dependencies, suspension, and continuation; its collaboration ledger is not an implementation of the Abyss's complete knowledge structure. The hand-written FSM in Abyss T4 only borrows survival and recovery ideas; neither it nor a collaboration ledger establishes complete knowledge learning, nine operators, or an autonomous coding system.

## Running and interpreting evidence

These commands run only Hongchenxian's offline tests. They do not train an Abyss model:

```sh
node --version  # Previously validated environment: Node.js 24.22.1
npm test
```

These Node tests require no npm install, Python, official model SDK, or API key. Tests create synthetic data in temporary directories. The default guard rejects common Node network entry points to prevent accidental calls; it is not a hostile-code sandbox. Do not supply real data paths or credentials.

The Abyss has separate Python installation and experiment entry points; see its [reproducibility notes](projects/the-abyss/implementation/docs/REPRODUCIBILITY.en.md). They name 12 foundation contract-test files and optional `test_t1.py`; none was run for this integration. Other tests can train models, and T4 starts its own subprocesses and injects hard exits. Static adaptation of new-run entry points does not establish that existing run directories or weights can be moved directly.

| Record | Scope |
|---|---|
| [Earlier VALIDATION](evidence/VALIDATION.json) | The earlier checkpoint's 72/72 Hongchenxian offline tests, not Abyss tests. Its “Abyss not yet integrated” statements remain historical |
| [This integration record](evidence/ABYSS_INTEGRATION.json) | Abyss source inclusion and the present check scope, separate from the earlier record |
| [Abyss static report](projects/the-abyss/implementation/STATIC_CHECKS.json) | Parsing, structure, links, hashes, and other static checks, not execution or learning validation |
| [Source snapshot](projects/the-abyss/implementation/historical/SOURCE_SNAPSHOT.json) | Relative source paths and hashes; release adaptations may differ in bytes |

Earlier `SCAN_REPORT.json` and `SOURCE_MANIFEST.json` also retain their original checkpoint scope. They must not be read as covering the newly added Abyss files in the same check. Use the current `SHA256SUMS` and integration record for the assembled repository's integrity scope.

## Repository layout

- `projects/the-abyss/`: bilingual theory, sources, evidence boundaries, and selected research sources, plans, and historical summaries under `implementation/`.
- `projects/hongchenxian/`: source, synthetic tests, and bilingual documentation.
- `scripts/`: offline-call guard, candidate scan, and integrity verification.
- `evidence/`: source and validation records separated by checkpoint.
- `docs/`: shared exclusions and release checklist.
- `third_party/`: a separate upstream license record; it does not select this project's license.

Theory, source, historical summaries, and the present static checks are recorded separately. No claim is made of completed recovery of ten real members, 72-hour continuous operation, general learning ability, a complexity breakthrough, or consciousness.

## Before publication

Read the [exclusions](docs/EXCLUSIONS.en.md), [release checklist](docs/RELEASE_CHECKLIST.en.md), and [third-party notices](THIRD_PARTY_NOTICES.en.md). Do not upload the original working directory wholesale. Real sessions, private conversations, accounts, credentials, original training data, and unreviewed operational records are excluded.

The [material-source notes](projects/the-abyss/implementation/docs/DATA_SOURCES.en.md) still identify incomplete provenance/licensing for the optional 119M backbone and a missing from-scratch `corpus_index.sqlite` generation path. These gaps preclude claiming a reproducible complete material pipeline. Corpora, tokenizers, and pretrained weights are not bundled, and T1–T10 synthetic experiments do not depend on that branch.
