# G1: complete ten-seed results from independent execution 3

[中文](README.md) · [Original preregistration](../PREREG.md) · [Configuration](../PLAN.json) · [Earlier two-seed history](../RESULTS.en.md)

**This execution completed 10/10 balanced seeds and 140/140 experimental cells.** It is a new execution in an isolated directory using the original frozen inputs, source and research configuration, not a resume or append in the original two-seed directory. Seeds are `2026110700–2026110709`. The earlier two-seed evidence remains historical and **is not pooled with duplicate seeds here to claim 12 seeds**. The recorded finish time converts to **2026-11-06 17:52:38 UTC**; the directory date is an experiment identifier.

The ten-seed results retain a benefit from sharing within supplied reference families under sparse supervision; equally sized random sharing lacks that benefit. With more supervision, the family arms' mean overall advantage disappears. This concerns supplied structural priors and hard parameter sharing on a fixed synthetic task, not optimal granularity for natural knowledge, autonomous package formation/splitting or a complete AI system.

## Task, grouping and fixed conditions

Each seed generates 96 atoms once (12 reference families of 8 members), 2,048 unordered object pairs and two world-specific questions per pair. Atomic identities, histories, queries, winners, labels and original splits stay fixed. Evaluation uses only the original `test`: 512 unordered pairs or 1,024 world-specific questions per seed. The two worlds repeat a pair and are not independent replicates.

The learner allocates 96 scalar slots and scores comparisons as `world_sign * (w[group(A)] - w[group(B)])`. Resolving A/B from visible histories and queries, and world inversion, are supplied rules. Nested training pools select 64/512 pairs with one world instance per pair. Every arm starts at zero, receives 4,096 presentations, uses learning rate 0.05 and no regularization. Data, labels and presentation order match across arms within each seed and supervision regime. Same-slot comparisons do not update weights but still consume presentation budget.

- `atomic`: one independent score per atom.
- `family2/4/8`: random nested grouping within generator-supplied reference families, without consulting hidden values to select groups.
- `random2/4/8`: random nested grouping across all atoms, matched to the corresponding family arm for group size and count.

The intervention changes the mapping from atoms to shared score slots. Families are supplied priors, not discoveries. Allocated slots stay fixed, but independent scores decrease from 96 to `96 / group size`; effective capacity and FLOPs are not claimed equal. Targets remain atomic winners, with half credit for same-slot ties. The 512-pair condition names the selected pool: finite random presentations actually cover 511 distinct pairs in four seeds and 512 in six. Unpresented pairs do not count toward observed graphs.

## All 14 cells

Values are read from [SUMMARY.json](SUMMARY.json). Accuracy is in percent; `±` denotes the **sample standard deviation across ten seeds**. Δ is the within-seed paired difference from atomic, in percentage points (pp); its SD is computed after differencing per seed, not propagated from two independent means. SD is not a confidence interval. These are descriptive comparisons, without significance claims. Within-/cross-package strata always use the same original reference families, not the current sharing groups. Their displayed values are seed means; SDs and individual seed values remain in the summary.

| Selected training pairs | Grouping | Accuracy mean ± SD (%) | Δ atomic mean ± SD (pp) | Original within-package mean (%) | Original cross-package mean (%) |
|---:|---|---:|---:|---:|---:|
| 64 | atomic | 69.70 ± 3.46 | +0.00 ± 0.00 | 57.32 | 70.50 |
| 64 | family2 | 74.48 ± 3.29 | +4.79 ± 2.96 | 51.92 | 76.05 |
| 64 | family4 | 78.93 ± 2.83 | +9.23 ± 3.58 | 51.19 | 80.97 |
| 64 | family8 | 82.56 ± 2.86 | +12.86 ± 4.87 | 50.00 | 84.97 |
| 64 | random2 | 63.97 ± 5.77 | -5.72 ± 3.80 | 51.69 | 64.80 |
| 64 | random4 | 59.99 ± 3.58 | -9.71 ± 3.79 | 49.35 | 60.76 |
| 64 | random8 | 55.21 ± 3.33 | -14.48 ± 4.10 | 47.00 | 55.79 |
| 512 | atomic | 86.66 ± 1.19 | +0.00 ± 0.00 | 71.30 | 87.83 |
| 512 | family2 | 86.46 ± 1.94 | -0.20 ± 1.91 | 62.87 | 88.25 |
| 512 | family4 | 86.23 ± 1.70 | -0.43 ± 1.97 | 54.59 | 88.54 |
| 512 | family8 | 85.25 ± 2.27 | -1.41 ± 2.06 | 50.00 | 87.88 |
| 512 | random2 | 72.70 ± 3.87 | -13.96 ± 3.84 | 55.18 | 73.92 |
| 512 | random4 | 65.07 ± 3.29 | -21.59 ± 3.28 | 51.87 | 66.06 |
| 512 | random8 | 59.12 ± 3.72 | -27.54 ± 3.58 | 54.92 | 59.42 |

At 64 pairs, every family arm has a positive difference from atomic in 10/10 seeds; every random arm has a negative difference in 10/10. At 512 pairs, positive/negative seed counts are 4/6 for family2, 5/5 for family4 and 2/8 for family8; all random differences remain negative. This does not identify a universally optimal granularity.

**The change from the early result remains visible:** the original two-seed report gave family2 a **+0.59 pp** difference from atomic at 512 pairs. The full ten-seed result is **−0.20 ± 1.91 pp**. This is a descriptive update over the complete seed set. It neither erases the earlier evidence, presents a near-zero mean as a stable benefit, nor claims a statistically established reversal.

## Paired controls against equally sized random sharing

These are within-seed `family(size) − random(size)` differences, in pp, not differences from atomic. Every individual seed difference in these six cells is positive. This demonstrates the role of a supplied family prior in this task, not autonomous discovery of those families.

| Selected training pairs | Group size | family − random mean ± SD (pp) |
|---:|---:|---:|
| 64 | 2 | +10.51 ± 6.07 |
| 64 | 4 | +18.94 ± 4.46 |
| 64 | 8 | +27.34 ± 5.13 |
| 512 | 2 | +13.77 ± 4.19 |
| 512 | 4 | +21.16 ± 4.03 |
| 512 | 8 | +26.13 ± 4.33 |

## Within-package detail and comparison graphs

Aggregate gains coexist with lost atomic distinctions. Family8 has **50%** within-family accuracy by construction: every atom in a family shares one score and ties receive half credit. This is not a learned achievement. At 64 pairs, atomic's within-/cross-family means are **57.32%/70.50%**, versus **50.00%/84.97%** for family8. At 512 pairs they are **71.30%/87.83%** and **50.00%/87.88%**. Within-family test strata contain only 21–46 unordered pairs per seed; cross-family questions dominate. Overall accuracy cannot replace within-family discrimination measures.

At 64 pairs, 64–77 atoms were actually seen, leaving 19–32 unseen, and atomic comparison graphs have 32–36 components. At 512 pairs, every seed sees all 96 atoms and its graph is connected. Sharing may transmit a supplied prior to unseen members or connect otherwise disconnected comparison components; those mediators were not isolated. Shared-slot collisions and original within-/cross-family strata are different partitions. Distinct slots can also lose information when different atomic pairs mapped to a group pair require opposite winners.

The post-hoc lookup reference in the summary uses test labels to choose the majority winner for each unordered group pair, with half credit for same-slot ties. It diagnoses conflicts after aggregation and is not used for training or arm selection. It is more flexible than the shared-scalar ranker. Neither it nor the separate reference that knows the winning group and randomly resolves same-slot ties is advertised as an information-theoretic upper bound for arbitrary models.

## Execution, resources and evidence scope

[SOURCE_EXECUTION.json](SOURCE_EXECUTION.json) records a separate execution after the earlier resource stop: research parameters and resource thresholds remain unchanged, prior receipts are not copied as new results, and prior evidence is preserved. Original PREREG, PLAN and frozen files retain their historical timestamps and wording; this is not retrospective preregistration of a new design.

**Independent scoring audit passed.** The audit recomputed all reported evaluation metrics and summaries from frozen inputs, saved weights and receipts for all 140 cells; they agree within absolute tolerance `1e-12`. The 28 receipts overlapping the earlier run match apart from completion timestamps, and all 53 files in the original attempt2 remain unchanged. Online training losses were checked only for finite values, planned checkpoints and noncollapsed update counts; they were not recalculated by training. Execution3 itself was an actual run; the audit recalculated from saved weights and **did not train again**. See [INDEPENDENT_AUDIT.json](INDEPENDENT_AUDIT.json) and [VERIFICATION.json](VERIFICATION.json) for evidence scope.

[RUN_STATUS.json](RUN_STATUS.json) records ten complete seeds and 140 receipts. [RESOURCES_run.json](RESOURCES_run.json) records **2.546875 CPU seconds, 25.749 wall seconds and 37.18 MB RSS at completion, with no GPU use**. RSS is not a peak measurement. These measurements cover this run stage, exclude original preparation costs and are not cross-machine performance guarantees. Throttling is cooperative, not an operating-system hard cap.

Published materials are limited to summaries, status, resources, execution notes and a separately supplied independent audit. **Generated input data and individual receipts containing weights are omitted.** The public package therefore cannot directly recompute these historical weight results. Numbers here come from the existing summary; any verification must state the local evidence it actually inspected. This public digest does not replace the audit's conclusions.

## Independent reproduction entry

The intended location is `projects/the-abyss/research/g1-granularity-20261107/followup-20261107-execution3/`. Read the parent [PREREG.md](../PREREG.md), [PLAN.json](../PLAN.json), [pilot.py](../pilot.py), [report.py](../report.py) and [README.md](../README.md). Preserve the required source layout in a new isolated directory, then prepare data, freeze, execute and generate evidence for that new run. Do not treat this page's results or a historical FROZEN as the new run's freeze, and do not overwrite an existing evidence directory. CPU 22 is an original-environment setting; adapt and record it before the first freeze elsewhere. If a resource gate stops execution, retain the incomplete state.

This result only tests synthetic scalar-sharing tradeoffs under supplied family priors. It is not a rerun of the T1 neural model, T11 or v18.1, does not test attention, and does not establish natural knowledge formation, semantic purity, optimal aggregation granularity or a complete memory-and-learning system.

