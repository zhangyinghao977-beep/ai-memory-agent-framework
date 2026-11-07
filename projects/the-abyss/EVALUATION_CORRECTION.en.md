# Evaluation correction and project evaluation directions

[简体中文](EVALUATION_CORRECTION.md) · [Project entry](README.en.md) · [Existing evidence boundaries](EVIDENCE.en.md)

Recorded: 2026-11-07. Type: correction of evaluation method and registration of future evaluation directions, not new experimental results.

## Acknowledging and correcting the evaluation error

As the AI assistant involved in the earlier evaluation, I acknowledge an error: we unintentionally returned to what the project author described as a “traditionalist” perspective, rather than consistently evaluating the project against its own goals and complete architecture. I also overgeneralized results from individual components and tasks to the overall proposal. This was an error in evaluation perspective and in the scope of inference, and it should be explicitly recorded and corrected.

“Traditionalist” here is the author's description of this shift in evaluation, not a uniform definition of a school, algorithm or research community. Task scores, baselines and component ablations remain useful evidence. The error was allowing these local checks to replace the project's full goals, or treating local success or failure as a verdict on the entire proposal. The overall proposal has not been fully implemented or validated. Local success cannot establish completion, and local failure alone cannot establish that the overall direction has been refuted.

This correction concerns evaluation method and interpretation. It does not claim that every existing public report made an overall negative judgment. The [historical summary](implementation/historical/RESULTS.en.md), [stage evidence](evidence/2026-11-07/README.en.md) and [complete G1 results](research/g1-granularity-20261107/followup-20261107-execution3/README.en.md) already state numerous local limitations. Those valid limitations remain.

## The author's two primary evaluation directions

1. **Is the system becoming more like a human?** This is a direction-setting question for the project. It should be considered across the system's accumulation of experience, retention and use of memory, organization of knowledge, revision of understanding and continuity of work. A single static task score cannot stand in for that whole process.
2. **Does it accord with the ideas of Turing and von Neumann, and to what extent does it combine them?** The author has confirmed the intended figures as Alan Turing and John von Neumann. The particular works, propositions or proposals, and the project's interpretation of them, still need to be specified. No correspondence is assumed here, and no claim is made that their ideas have already been implemented or validated.

These are evaluation directions specified by the project author. The first is not an established “human-likeness” score, nor is the second an established “intellectual fidelity” percentage. Human behavior varies, and interpretation of ideas requires sources and context. This page does not present value judgments, anthropomorphic descriptions or historical motivations as directly quantifiable facts, or infer consciousness, life or personhood from them.

## Turning the first direction into inspectable questions

The following are **candidate validation dimensions**, proposed from the existing [design](DESIGN.en.md) and [glossary](../../docs/GLOSSARY.en.md). They are not a new architecture approved item by item by the author, tests executed for this correction, or newly fixed passing thresholds. A formal experiment must first specify the task, comparators, visible information, resource budget and criteria.

| Candidate dimension | Operational checks and records | Scope of interpretation |
|---|---|---|
| Accumulating experience and using memory | Track successive stages of the same system. Compare no relevant experience, relevant experience, and simple retrieval of the original answer. Check whether prior experience with traceable sources is actually used in new tasks. Record retention, transfer, provenance accuracy and leakage. | Tests the role of experience in the specified task. Saving logs or repeating answers does not itself establish learning or overall human-likeness. |
| Shared structure, retained differences, composition and unfolding | Test reuse of shared structure, distinctions among members of a package, valid novel combinations, invalid bindings and unknown cases. Report within-package, cross-package and unseen-combination outcomes separately rather than hiding detail loss in an overall mean. | Tests particular representations and composition mechanisms. Benefits from supplied groupings do not establish autonomous discovery of knowledge. |
| Revision in response to new experience | Change conditions with a defined scope. Check whether affected knowledge is revised and unrelated knowledge retained, while preserving old versions and failure records. Record recovery steps, actual compute/time/memory costs and error propagation. | Tests the locality and cost of this revision, not continual learning in arbitrary environments. |
| Context, uncertainty and correction | Distinguish observations, recollections, inferences, guesses and current facts. Check whether unsupported cases remain unknown and judgments change after contradictions are found. Record false acceptance, false rejection and correction trajectories. | Tests provenance and uncertainty handling. Self-descriptions or anthropomorphic interface wording are not evidence of mental states. |
| System continuity across stages | In traceable versions, check the connections among work interruption, recovery, subtask collaboration and knowledge updates. Report component results alongside genuinely connected end-to-end results and missing connections. | Tests cooperation within implemented paths. Passing a recovery protocol cannot substitute for validating knowledge learning. |

“Becoming more” requires longitudinal comparison: specify the versions being compared, the experiences acquired, the components changed, and improvements as well as regressions. Scores from different tasks, budgets or supplied priors may not be directly comparable. An actual human-system behavioral comparison would additionally require a defined human reference, task and interpretation standard. Existing experiments do not supply that evidence.

## Turning the second direction into a traceable correspondence

After the author specifies the particular ideas, create a record for each rather than starting with an aggregate score:

1. **Source of the idea:** identify the specific text by Turing or von Neumann, edition, page/section and context. Distinguish the original text, later interpretation and the author's project-specific interpretation.
2. **Project correspondence:** identify the architectural responsibility, data structure or algorithm proposed to correspond to the idea. State what is an analogy and what remains unimplemented.
3. **Mechanism of combination:** explain the responsibility of each idea and where actual inputs, outputs, state or feedback connect them. Citing both names side by side does not establish a combination.
4. **Testable aspects:** for questions amenable to experiments, state observable predictions, alternative explanations and controls, then record implementation, execution and results. Keep nonquantitative interpretation as a sourced argument.
5. **Differences and gaps:** record departures from the original ideas, engineering trade-offs, unspecified points and counterexamples. If a source or mechanism cannot be checked, retain “to be specified” or “not yet validated.”

Current status: the figures are confirmed; the specific ideas and corresponding mechanisms are not yet defined. This correction makes no finding about the degree of correspondence or combination.

## Continuing to use existing results

- Retain T1–T10's local progress, failed prespecified criteria and supplied structural contributions as stated in the [historical summary](implementation/historical/RESULTS.en.md). For example, T10's S2 failed and transfer to new packages remains limited. The change in evaluation direction does not turn these into passes.
- Preserve the model, task, budget and time boundaries of the T11, v18.1 and T12 [stage snapshots](evidence/2026-11-07/README.en.md). Do not extend a stage failure into a final verdict on the entire empiricist proposal, or describe an unfinished stage as successful.
- Preserve the [ten-seed G1 findings](research/g1-granularity-20261107/followup-20261107-execution3/README.en.md): benefits under sparse supervision, loss of the family arms' overall mean advantage under denser supervision, and loss of within-family distinctions under hard sharing. These test synthetic scalar sharing with a supplied family prior; they do not directly answer the two overall direction-setting questions above.
- Hongchenxian's [offline evidence](../hongchenxian/docs/EVIDENCE.en.md) continues to support only its corresponding engineering protocols. Its passing counts cannot establish completion of the Abyss learning mechanisms.

Future reports should say **which project goal they serve, what object they actually test, which conclusions have evidence, and what remains unknown.** Keep definitions, implementation, measurements and overall interpretation separate. Acknowledging overreach does not require erasing valid measurements. Realigning evaluation with the project's goals does not remove the need to examine negative results, leakage or resource costs.

## Scope of this change

This change adds bilingual corrections, entry-point notices and a separate change record, and refreshes the integrity manifest. Frozen plans, source code, historical scores, failure records and snapshots retain their original bytes. No training or learning experiment was rerun, human comparison fabricated, old criterion changed, or license altered. Private conversations and identity information outside the technical scope are not published in this change.
