# 深渊 / The Abyss

[中文](README.md) | [English](README.en.md)

**Evaluation correction:** [Evaluation errors and two primary directions](EVALUATION_CORRECTION.en.md). This acknowledges a misplaced evaluation perspective and component-to-system overgeneralization, and records human-likeness and correspondence with and combination of Turing’s and von Neumann’s ideas as directions, without rewriting historical results.

**Latest G1 execution:** [Complete ten-seed results](research/g1-granularity-20261107/followup-20261107-execution3/README.en.md), preserving the original resource stop and changes from the small initial sample.

**Glossary:** [Consolidated terminology and event-chain section](../../docs/GLOSSARY.en.md), a dated discussion snapshot preserving historical definitions and experiment boundaries.

[New evidence and granularity pilot (2026-11-07)](evidence/2026-11-07/README.en.md) separates historical training summaries, ongoing stages, and the new G1 pilot that completed only 2/10 seeds.

1. **Logic is the path that makes knowledge reachable.**
   逻辑是知识的可达路径。

This is the project's stated theoretical proposition, not an empirically established conclusion. No additional theorem is inferred from it here.

The Abyss is an **unfinished AI approach to memory and learning**. It studies how to retain experience, form traceable memories and reusable knowledge, unfold knowledge for tasks, and revise it locally with new experience. A base LLM does not itself provide the persistent state and complete learning mechanisms proposed here; the current implementation also does not complete the overall design.

This directory retains the de-identified theory digest and adds selected original research sources with adaptations under [implementation](implementation/README.en.md): 65 core Python files, 25 `test_*.py` files, 31 experiment Python files including the shared helper, and 11 plans. They provide a memory foundation, knowledge packages, an event-chain AST, and T1–T10 synthetic experiment entry points. This is not a distribution of the entire original workspace.

Empiricist event chains represent objects, relations, conditions, and transitions. Hongchenxian work-event chains record work calls, dependencies, receipts, and recovery. Their work processes have a mapping, but running a collaboration ledger cannot be treated as implementation of knowledge-learning algorithms. T4's hand-written FSM only borrows survival and recovery ideas.

## Reading order

1. [Proposal and current concepts](DESIGN.en.md): the central knowledge carrier, two forests, finding commonality while preserving differences, reference frames, training direction, and resource boundaries.
2. [Code entry point](implementation/README.en.md) and [reproducibility notes](implementation/docs/REPRODUCIBILITY.en.md): included modules, dependencies, explicitly selected lightweight test candidates, and experiment commands.
3. [Implementation and evidence boundaries](EVIDENCE.en.md): what theory, selected source, historical summaries, and present static checks support.
4. [Historical results](implementation/historical/RESULTS.en.md): the scope and results below expectations from T1–T10.
5. [Sources and editorial notes](SOURCES.en.md) and [material sources](implementation/docs/DATA_SOURCES.en.md): theory provenance, external materials, and missing reproduction steps.

`DESIGN` and `SOURCES` retain their earlier theory-compilation content and wording. Progress statements there describe that earlier point, not a current absence of code. See [this integration record](../../evidence/ABYSS_INTEGRATION.json) for current inclusion status.

## Current validation scope

Source integration received static review and organization only; see the [static report](implementation/STATIC_CHECKS.json) and [integration record](../../evidence/ABYSS_INTEGRATION.json). No Abyss installation, project import, pytest run, training, or independent reproduction was performed. Having code and test files is not a passing-test result.

T10 historically has 50/50 receipts, but S2 failed and generalization to unseen packages remains unresolved. Rule-construction formulas, comparators, windows, and parts of the structure are human-designed. Local results on synthetic tasks do not establish general knowledge learning. Hongchenxian's earlier 72/72 offline tests support only its mechanical protocol scope and cannot substitute for Abyss learning experiments.

## Included and excluded material

The theory documents are technical summaries based on existing design documents. `implementation/` contains selected research sources and adaptations, plans, and historical summaries. These categories have different provenance and evidence requirements; they are not a complete copy of original conversations or the working directory. Explicit corrections in later versions take precedence over earlier shorthand; unresolved mechanisms remain unresolved.

Private quotations and conversation transcripts, personal identities and accounts, message identifiers, private addresses, absolute paths on personal computers, raw training data, pretrained weights, runtime databases, raw training receipts, and secret values are excluded. External data and model materials are not bundled.

External-material documentation does not mean that the materials are bundled or fully reproducible. The optional 119M backbone still lacks complete provenance and licensing information, and a from-scratch `corpus_index.sqlite` generation path is missing. T1–T10 use code-generated synthetic data and do not depend on that material branch.

The project license remains undecided; see [license status](implementation/LICENSE-STATUS.md) and [third-party notices](../../THIRD_PARTY_NOTICES.en.md). This integration grants no code or material license on behalf of the rights holders.
