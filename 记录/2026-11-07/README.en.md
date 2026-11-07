# Experiment process note: v19 and T12–T25

[简体中文](README.md) · [Record index](../README.md) · [Earlier public snapshot](../../projects/the-abyss/evidence/2026-11-07/README.en.md)

Recorded on 2026-11-07 from saved materials available by approximately 14:18 UTC that day. This is a historical snapshot, not a current runtime status. Compilation involved read-only review, without rerunning training, model evaluation or third-party API experiments.

## Process and status

1. **Little Witch (Gemini), v19:** A partial Empiricist implementation combines multistep context, FSM suspension/resumption, associative message pools, cold paging, merging and failure records, compared with FIFO and no-FSM settings. Six-arm, three-seed aggregate receipts exist. Simulated ticks are not measured hardware speedups; recovery given correct external feedback is not autonomous answer discovery.
2. **Little Nun (Claude), T12:** Old knowledge packages are learned before new packages are introduced, with replay and other settings compared. v3/run_002 has 20 old-stage and 20 continual-learning result files. Some predictions miss their original thresholds; complete receipts do not mean all hypotheses passed.
3. **T13–T23:** Learning slices, scripted bodies and black-box Agent interfaces progressively compare originals, summaries, differences, RAG, chat and active retrieval. T23 makes 8,854 queries across 1,688 selection tasks, but existing judgments may persist; 343 tasks reach the five-round cap. Models, rules and budgets differ, so no unified ranking is claimed.
4. **T24:** Review confirms smoke materials for the five-member, role and meeting prototype. The planned formal ten-seed experiment was not run.
5. **T25:** A five-member pool and solo loop use 12 public sources in a planned 72-hour study. The inspected run_002 snapshot contains only its first cycle, starting at 14:03:40 UTC. It is not a completed three-day study; a single PID observation also cannot establish that execution stopped.

## Failures and corrections

- T18 encountered empty usage and service 500 errors. Later change records describe retries and request-hash-checked replay; the older frozen version remains.
- T20 corrects its retrieval denominator from tool turns to tasks. T22 changes W5, which has no relevant observations, to indeterminate. These are reporting corrections, not rewrites of frozen records.
- T23 retains truncations, invalid choices and failed summaries. Reaching a retrieval cap is not convergence.

## Provenance, roles and next steps

Little Witch supplies the v19 materials and Little Nun supplies T12–T25. The user provides questions, corrections and experiment direction; the current compilation assistant reviews saved artifacts, summarizes and publishes. Nicknames identify provenance, not architecture categories. Cross-workspace artifact review does not establish direct conversation between participants.

The studies separately cover partial Empiricist implementations, scripted demonstrations, black-box memory interfaces and Hongchenxian-oriented prototypes. They do not add up to complete-system validation. This note changes no architecture and grants no new experiment authorization.

For now this directory records the process. Related experiment code, dependencies and reproduction entry points require later review and organization. Raw private chats, prompts/replies, news text, complete receipts, models, databases and credentials are not included. Existing public files remain in place.
