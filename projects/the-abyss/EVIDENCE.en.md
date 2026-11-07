# Implementation and evidence boundaries

[中文](EVIDENCE.md) | [English](EVIDENCE.en.md)

**Subsequent evaluation correction:** [Evaluation directions and inference boundaries](EVALUATION_CORRECTION.en.md). The local evidence limits on this page remain valid. The two overall evaluation directions are recorded separately; local success or failure cannot substitute directly for an overall judgment.

## What this compilation can establish

- [implementation](implementation/README.en.md) now contains selected original research sources and release adaptations: 65 core Python files, 25 `test_*.py` files, 31 experiment Python files including the shared helper, and 11 plans. Test helpers and a static-check tool are additional files; these counts are not passed-test counts.
- Validation for this integration is static only, recorded in [STATIC_CHECKS.json](implementation/STATIC_CHECKS.json) and [ABYSS_INTEGRATION.json](../../evidence/ABYSS_INTEGRATION.json). It did not install dependencies, import the project, run Abyss tests, train, or independently reproduce historical results.
- The 2026-10-22 core design draft offers implementation breakdowns and validation suggestions, explicitly without claiming implementation or experimental success.
- Glossary v0.57 was updated on 2026-11-02, later than the date retained in its filename. It contains conceptual updates, historical discussion, and unresolved mechanisms; the entire document cannot be treated as proof of a complete implementation.
- The 2026-10-10 overall architecture snapshot identifies itself as historical. It reports some local integrations and experiments, not a current specification or an independent reproduction performed for this compilation.
- The 2026-11-05 Hongchenxian working-event-chain audit clarifies the cross-project boundary. Its evidence from the original architecture consists of excerpts retaining line numbers and hashes, not the complete original specification.

## Evidence by subject

| Subject | Available evidence | Scope in this public preview |
|---|---|---|
| Central knowledge carrier, two forests, commonality with differences, reference frames | Design and later definitions; source for local storage and package structures | The complete architecture remains a proposal; local structures do not establish the whole system |
| Experience, memory, knowledge packages, and provenance | `experience.py`, `memory.py`, `registry.py`, `learning_store.py`, and related modules | Interfaces and constraints exist; their contract tests were not run for this integration |
| Empiricist event-chain AST | Structures, occurrences, bindings, and transition records in `event_ast.py` | A local representation exists; it does not complete all nine operators, automatic formation, or semantic-equivalence mechanisms |
| Substitution revision, cross-layer inputs, and local training | T1–T4 source, plans, and historical summaries | Local implementations and observations on controlled tasks, not complete learning over arbitrary knowledge structures |
| Caching, packaging, loops, suspension and recovery | `valve.py`, storage code, the T4 runtime, and related designs | Some boundaries and recovery mechanisms have source; T4's FSM is fixed by hand, not autonomously formed |
| Divide-and-conquer streaming with very small networks | v0.55 requirements and staged/local training code | Specific implementations can be inspected; no execution, residency tracing, or profiling in this integration verifies overall compliance |
| Historical knowledge indexing and experiential recombination | Reports of local paths in the October 10 snapshot | Retain the existence of historical reports without restating them as current whole-system acceptance |
| Hongchenxian working event chains | Separate working-chain audit and offline protocol prototype | A limited subset of work recording, invocation, dependencies, suspension, and continuation |

## What Hongchenxian carries forward

Persistent work records for black-box Hongchenxian Agents can carry task processes, model and tool call results, dependencies, intermediate products, and replay clues. They provide records of collaboration state, without promoting participants' statements to world truth or replacing trusted execution evidence with logs.

These collaboration records do not establish completion of the empiricist generalized AST's internal computation, nine operators, knowledge-combination learning, internal indexing operators, or separate learning event chains. The empiricist sources now include partial AST implementations and learning experiments; assess them using their own code and evidence rather than borrowing Hongchenxian results. Discussing learning within a working chain remains a work-process discussion. A recorded failure or successful call cannot alone establish learning.

The smallest memory paragraph must not be mechanically equated with a protocol event. Process structures and concrete occurrences, original knowledge versions and particular uses, local results and completion of the overall task also require distinct contracts and evidence.

## Implementation material and current review status

The material is divided into four categories that cannot substitute for one another:

1. **Theory:** [DESIGN](DESIGN.en.md) and [SOURCES](SOURCES.en.md) retain concepts, provenance, and unresolved mechanisms; they are not implementation evidence.
2. **Selected research sources:** the [core modules](implementation/project/empirical_core/) and [experiment entry points](implementation/experiments/) contain actual research code with de-identification, path, and resource adaptations. See [CORE_CHANGES](implementation/docs/CORE_CHANGES.md), [experiment changes](implementation/docs/EXPERIMENT_CHANGES.md), and [T1–T4 changes](implementation/docs/EXPERIMENT_CHANGES_T1_T4.md).
3. **Historical summaries:** [RESULTS](implementation/historical/RESULTS.en.md) summarizes existing T1–T10 runs and limitations. These are not new runs of the public copy, and the complete original receipts, databases, and weights are not included.
4. **Present static validation:** [STATIC_CHECKS](implementation/STATIC_CHECKS.json) and the [integration record](../../evidence/ABYSS_INTEGRATION.json) state their check scope. Parsing, hashes, or file existence do not establish successful execution, learning, or scientific comparability.

`DESIGN` and `SOURCES` retain their original wording from the earlier theory-compilation stage. Historical phrases such as “candidate under review” do not override the present integration status. Use the categories here and the integration record for the current code scope.

T10 historically has receipts for 50/50 tasks and a report, but **S2 failed and generalization to unseen packages remains unresolved**. Completion counts are not success rates. T8–T10 still use human-written rule-construction formulas, comparators, windows, and parts of the structure. Local synthetic results do not establish complete autonomous knowledge formation or general continual learning.

The [reproducibility notes](implementation/docs/REPRODUCIBILITY.en.md) now provide dependencies and entry points for new runs, without execution validation in this integration. The 12 foundation contract-test files plus optional `test_t1.py` are lightweight candidates only. Other tests may train, and T4 injects hard exits into its own subprocesses. Portability adaptations for new runs do not establish verified migration of existing run directories or weights.

The [material-source notes](implementation/docs/DATA_SOURCES.en.md) retain two key gaps: the optional 119M backbone lacks complete versioned provenance, public availability, and licensing evidence; the large-corpus pipeline lacks a complete from-scratch generator for `corpus_index.sqlite` from downloaded materials. These materials are not bundled, and a reproducible complete material pipeline is not claimed. T1–T10 synthetic experiments do not depend on that branch.

The earlier [VALIDATION.json](../../evidence/VALIDATION.json) records 72/72 Hongchenxian offline protocol tests only. Its old Abyss status, scan, and source inventory remain records of that earlier checkpoint. The new inclusion is separately recorded in [ABYSS_INTEGRATION.json](../../evidence/ABYSS_INTEGRATION.json), rather than retroactively treating it as validation already performed in the past.

## Wording of conclusions

A working definition is a meaning adopted for the current discussion; a candidate remains revisable. Implemented requires code, run requires execution records, and passed requires acceptance results with explicit scope. These states must not be conflated. Unknown does not mean refuted, and limited success does not imply a universal guarantee.

This integration adds no performance, complexity, life, or consciousness conclusions from new execution. The O(n) work of standard minimum comparisons or conditional O(log n) reduction depth is general analysis, not a project measurement or a global complexity guarantee.
