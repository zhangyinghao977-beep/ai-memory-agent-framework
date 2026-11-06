# G1: aggregation and separation on a fixed task

[中文](RESULTS.md) · [Reproduction entry](README.md) · [Preregistration](PREREG.md) · [Configuration](PLAN.json) · [Combined evidence](../../evidence/2026-11-07/README.en.md)

**Follow-up:** [execution3 completed all ten seeds](followup-20261107-execution3/README.en.md). This page retains the original two-seed historical snapshot; its stopped status and numbers do not describe the later execution.

**Status: `INCOMPLETE_RESOURCE_STOP`. Only the first 2 of 10 planned seeds completed, covering 28/140 experimental cells.** Each completed seed contains all seven grouping arms and both supervision regimes. They are a prefix of the predetermined execution order, not seeds selected for favorable scores. Eight seeds remain incomplete; this is not a successful ten-seed reproduction.

This pilot was newly executed. It reuses the reviewed standard-library T1 generator with a new shared-scalar comparison learner. It is not a rerun of the original T1 neural model, T11, or v18.1, and does not test attention.

## Fixed task and grouping intervention

Each seed generates 96 atomic objects, 2,048 unordered object pairs and two world-specific questions per pair once. Atomic identities, histories, queries, winners, labels and original splits are preserved. Evaluation uses only the original `test` split: 512 unordered pairs, or 1,024 world-specific questions per seed. The two worlds repeat the same pair rather than providing independent replicates.

The learner allocates 96 scalar slots and scores a comparison as `world_sign * (w[group(A)] - w[group(B)])`. A/B resolution and world inversion are supplied rules. The nested supervision regimes contain 64 or 512 distinct training pairs, with one world instance per pair. Every arm uses zero initialization, 4,096 presentations and learning rate 0.05, sharing the same data, labels and presentation order. Same-slot comparisons consume budget but do not update weights.

- `atomic`: one independent score per atom.
- `family2/4/8`: random nested grouping within generator-supplied reference families, without consulting hidden values to select groups.
- `random2/4/8`: random nested grouping across all atoms, matched for group size and group count.

Reference families are supplied prior knowledge, not learned discoveries. Allocation stays fixed, but independent scores decrease from 96 to `96 / group size`; effective capacity and FLOPs are not claimed to be identical. Targets remain atomic winners. Same-slot ties receive half credit.

## Results from the two completed seeds

Accuracy is a seed-level mean. Deltas are paired percentage-point differences from `atomic` in the same seed. [historical/SUMMARY.json](historical/SUMMARY.json) contains individual seed results and sample standard deviations. With two seeds, these deviations are not confidence intervals; no significance claim is made.

| Grouping | Accuracy, 64 pairs | Delta vs atomic | Accuracy, 512 pairs | Delta vs atomic |
|---|---:|---:|---:|---:|
| atomic | 66.70% | +0.00 | 86.72% | +0.00 |
| family2 | 71.68% | +4.98 | 87.30% | +0.59 |
| family4 | 76.17% | +9.47 | 85.94% | -0.78 |
| family8 | 81.84% | +15.14 | 85.16% | -1.56 |
| random2 | 62.26% | -4.44 | 70.21% | -16.50 |
| random4 | 62.16% | -4.54 | 62.16% | -24.56 |
| random8 | 56.54% | -10.16 | 58.30% | -28.42 |

Under sparse supervision, sharing within supplied families improved overall accuracy; equally sized random groups did not show the same benefit. With more supervision, the advantage of larger groups diminished. The two seeds disagree on the direction of the `family4` delta at 512 pairs. The average `family2` gain there is only 0.59 points, insufficient to establish an optimal granularity.

Sharing also loses atomic detail. With 64 pairs, within-/cross-family accuracy is 68.03%/66.59% for `atomic` and 50.00%/84.61% for `family8`; with 512 pairs, it is 74.15%/87.77% and 50.00%/88.20%, respectively. The 50% within-family score of `family8` follows directly from sharing one score, rather than being a learned discovery. The within-family test strata contain only 46 and 36 unordered pairs in the two seeds; overall accuracy is dominated by cross-family questions.

## Comparison graphs and information loss

In both 64-pair seeds, only 72 atoms were actually presented, leaving 24 unseen atoms and 33 connected components in the atomic comparison graph. Both 512-pair graphs cover all 96 atoms and are connected. Sharing may propagate a supplied family prior to unseen members or connect otherwise disconnected comparison components. This is a plausible contributor, not an independently isolated mediator and not evidence of learned structure discovery.

Within-/cross-family errors use the same fixed reference partition in every arm. Seen status and connectivity use actually presented A/B endpoints. Current shared-slot collisions are reported separately. Different slots can also lose information: different atomic comparisons mapped to the same group pair may require opposite winners.

The post-hoc lookup reference selects the majority winner separately for each unordered group pair using test labels, with half credit for same-slot comparisons. It is more flexible than a shared-scalar ranking model and is used only to diagnose conflicts, never to train or select arms. The separate reference that knows the winning group and randomly resolves same-slot ties is not an information-theoretic upper bound for arbitrary models.

## Two protective stops and published evidence

The first attempt stopped during preparation under the resource gate, before any training or training freeze/receipts. Its [stop status](historical/FIRST_ATTEMPT_PREPARE_STATUS.json) and [resource record](historical/FIRST_ATTEMPT_RESOURCES_prepare.json) are retained. The second attempt only corrected the resource sampling window by pausing this process for 0.4 seconds while sampling; research settings and stop thresholds were unchanged. See [ATTEMPT_NOTE.md](ATTEMPT_NOTE.md).

The second preparation completed all ten seeds. The training run completed two balanced seeds in order, then stopped when paused sampling found the selected CPU at 53.8%, above its 50% threshold. Mean host load was 53.98%, below its separate 60% threshold. The training process used 0.46875 CPU seconds and about 5.01 wall seconds, with no GPU. No threshold was subsequently relaxed and no further rerun was made. These times cover training-run execution only; preparation has a separate resource record.

- [Historical run status](historical/RUN_STATUS.json), [preparation resources](historical/RESOURCES_prepare.json), [run resources](historical/RESOURCES_run.json)
- [Historical frozen hashes](historical/FROZEN.json), [data audit](historical/DATA_AUDIT.json), [historical verification](historical/VERIFICATION.json)
- [Complete summary](historical/SUMMARY.json)

The local evidence review recomputed accuracies, conflict references, graph statistics and summary arithmetic from frozen data and 28 receipts, and checked source/data hashes without retraining. This public directory contains selected code, summaries and audit/hash/resource records, **omitting ten generated-data files and 28 individual receipts containing weights**. The historical `VERIFICATION.json` status of `passed` describes the local evidence available at checking time. It does not certify that every original input is published; running the reporting script here cannot directly reconstruct the old history.

The `training_started: false` field in `historical/FROZEN.json` is a pre-training snapshot, not a claim that training never occurred. The ten seeds in `DATA_AUDIT.json` establish completed preparation only. Training completion is the two balanced seeds recorded in `RUN_STATUS.json`.

The published code preserves research parameters. Its default Windows CPU 22 is an environment-specific setting: read [README.md](README.md) before use. In a fresh isolated directory, `prepare` generates new root-level `data/` and `FROZEN.json`. The old `historical/FROZEN.json` is provenance, not a freeze to move into the new run's root. Directory dates are experiment identifiers; JSON UTC timestamps identify actual events.

This incomplete pilot supports only a local account of supplied structural priors, supervision sparsity and hard parameter sharing on a fixed synthetic comparison task. It does not establish optimal granularity for real knowledge, autonomous grouping or splitting, attention superiority, or a complete memory-and-learning system.
