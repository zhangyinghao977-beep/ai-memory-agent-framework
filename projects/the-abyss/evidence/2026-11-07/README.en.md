# The Abyss / 深渊: evidence checkpoint

[中文](README.md) · [Project entry](../../README.en.md) · [Structured results](RESULTS.json) · [Source snapshot and hashes](source_snapshot.json)

**Later G1 execution:** [New results for all ten seeds](../../research/g1-granularity-20261107/followup-20261107-execution3/README.en.md) are recorded separately. The text below retains the initial run and time-bounded snapshots of other tracks; original results and predictions are not rewritten.

Logic is the path that makes knowledge reachable. This states a research direction, not a complete theory established by the experiments below. The Abyss remains an incomplete AI scheme for memory and learning. This page separates implemented components, historical measurements and unverified hypotheses.

The v18.1 and T11 entries summarize original local receipts and code checks from their respective tracks; they were not independently rerun for this publication. G1 was newly executed but completed only part of its preregistered plan. Published summaries and source hashes do not include the original corpora, model weights or all raw receipts. Hashes identify sources; they do not replace omitted inputs or reproduction.

| Track | Recorded status | Evidence boundary |
|---|---|---|
| v18.1 purified grouping | Original record completed 3 seeds × 5 arms | Grouping, filtering, representation and replay changed together; not a single-variable granularity ablation |
| T11 fresh chains | Original record 40/40, 8 cells × 5 seeds | Chain diversity and relation embeddings on a fixed synthetic task |
| G1 fixed-task granularity | 2/10 balanced seeds, 28/140 cells; resource stop | Newly executed, but insufficient to establish a stable optimum |
| T12 continual learning | Intermediate v3 / run_002 stage; no complete overall result | Completed tf data do not support the original H1; no final track-level verdict |
| T13 slicing | Unfrozen, untrained draft | Not an executed experiment or measured result |

## v18.1: overall benefit and fine discrimination

These means cover all five arms in the original receipt. Except for sibling ranking, metrics are candidate-slot selection accuracies on answerable questions; Wiki uses the all-package validation set. Sources, standard deviations and selected fields are recorded in [RESULTS.json](RESULTS.json).

| Arm | TinyStories validation | Sibling ranking | Wiki zero-shot hot swap | Wiki after further learning | Old TinyStories retention |
|---|---:|---:|---:|---:|---:|
| full | 32.71% | 56.98% | 14.58% | 21.15% | 30.73% |
| pairwise_no_softmax | 36.04% | 57.08% | 13.75% | 22.40% | 31.04% |
| self_no_chain_attn | 31.56% | 56.04% | 13.75% | 21.56% | 26.56% |
| soft_wall_plus4 | 33.44% | 58.02% | 13.85% | 19.69% | 29.38% |
| no_lattice_glass | 25.73% | 56.98% | 15.21% | 18.65% | 24.27% |

The TinyStories accuracy gap between full and glass is not accompanied by a gap on this sibling metric. Full does not lead every metric; its mean zero-shot hot-swap accuracy is below glass. The sibling metric asks whether the true slot outscores the strongest same-package distractor; it is not word-sense accuracy conditional on selecting the correct package. Package-level filtering or another structural component is a possible explanation, not an isolated causal result.

`full` and glass simultaneously change lattice initialization, local reference representation and hard legality masking. Relative to v18, v18.1 also changes whole-word reconstruction, filtering, document-frequency/salience-based origin selection, origin exclusion, sealing old packages and old-question replay. Overflow aliases may map distinct words to the same member slot. The five arms do not separately sweep package capacity, origin thresholds or aliasing.

Thus `known impurity = 0` means that a predefined probe list was not matched, while `twin = 0` means origin cosines did not cross a specified threshold. Neither guarantees semantic purity. Slot accuracy does not demonstrate discrimination between words mapped to one slot.

## T11: more distinct chains did not produce monotonic gains

Each cell contains five seeds, 48,000 steps and batch size 128. Values below are mean two-candidate selection accuracies (`choice_two`) from the original records, not binary-answer accuracies. IID tests new questions over existing packages; new tests new packages. Chain count denotes the selector's distinct training pool, not package size.

| Selector / relation embedding | Distinct training chains | IID | new |
|---|---:|---:|---:|
| attn / zero | 65,536 | 99.950% | 65.873% |
| attn / zero | 262,144 | 94.658% | 59.091% |
| attn / zero | 1,048,576 | 59.938% | 52.173% |
| attn / zero | 6,144,000 | 51.699% | 50.158% |
| attn / off | 6,144,000 | 73.513% | 58.918% |
| attn / one | 6,144,000 | 50.325% | 49.861% |
| pair / one | 6,144,000 | 67.001% | 53.026% |
| pair / zero | 6,144,000 | 64.160% | 56.760% |

`zero` is a trainable zero-initialized relation embedding; `off` is zero-initialized and frozen; `one` uses the original trainable scale. Increasing the pool at a fixed update budget also changes average repetitions per chain. At the largest pool, each chain is presented once. These findings do not establish that more experience is harmful or that attention cannot learn. Earlier T10 results at 16,384 chains belong to a different condition and are not interchangeable with this table.

T11 fixes four synthetic objects per package and eight events per chain. Package membership is generator-supplied; object vectors grow from co-occurrence and remain fixed during selector training. New-package vectors have already used answer-free experience chains, so new is not a subsequent continual-learning result. The task selects the candidate supported by an ordinary event from the same package. Training supervises only the target object's binary answer: when both candidates have the same answer, the loss cannot distinguish their identities. Two-candidate chance accuracy is 50%. In contrast, v18.1 directly supervises candidate slots with cross-entropy and uses different question construction, legality filtering and trainable representations.

The two pair baselines also differ. T11 averages pairwise products passed through an MLP. v18.1 retains Q/K/V and replaces softmax with `tanh / L` in history attention and candidate-to-history cross-attention. T11 pair has 20,705 parameters versus 18,593 for attn; effective capacity and FLOPs are not matched. Differences between these tracks cannot be reduced to a change in grouping granularity alone.

## G1: directly holding the task fixed

See the [G1 results](../../research/g1-granularity-20261107/RESULTS.en.md) for methods, all arms and protective stops. G1 preserves atomic winners and changes only the mapping to shared scores while holding data, order, learner and update budget fixed.

With 64 supervised pairs, `atomic` reaches 66.70% and `family8` 81.84% (+15.14 points). With 512 pairs, they reach 86.72% and 85.16% (-1.56 points). Within-family questions in `family8` necessarily tie and score 50%. Random grouping does not show the same benefit.

Both sparse seeds have 33 atomic comparison-graph components and 24 unseen atoms; reference families are already supplied. The findings fit a local account of propagating an existing prior while sacrificing detail, not discovering knowledge structure. The two seeds completed in predetermined order before the resource gate stopped execution. They were not selected for favorable results, and eight seeds remain incomplete.

## T12 / T13 in progress

The fixed T12 snapshot is at 17:03:14 UTC. See [ongoing_snapshot.json](ongoing_snapshot.json) for status and [source_snapshot.json](source_snapshot.json) for source hashes. At that point v3 / run_002 had 16/20 old-stage receipts: both tf sizes were 5/5; tf_sup at 65,536 was 5/5 and at 262,144 was 1/5. Continual learning has no complete overall result yet. The original run_001 stopped after plan freezing and retains its zero-receipt status.

The frozen H1 required at least four of five tf seeds below 70% at each size. Completed tf data do not support that hypothesis; a general claim that TF cannot learn is unwarranted. Intermediate progress is not presented as a final result. T13 remains an explicitly unfrozen and untrained slicing draft.

The object/relation event chains in these empiricist experiments are distinct from Hongchenxian's work-event records. Theory, partial implementation, historical measurements and the new pilot have separate evidentiary scopes. None establishes completion of the whole memory-and-learning scheme.
