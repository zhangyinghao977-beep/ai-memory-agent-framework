# Stage 5 / DLC 04: from an agent to an AI architecture

[简体中文](STAGE5.zh.md) · [Base prototype and the first three DLCs](DLC.en.md)

**Status: theoretical design, with no model-level implementation yet.** Stage 5 is the transition from the Hongchenxian agent prototype to research on the AI architecture itself. DLC 04 is the extension that carries this transition. It does not replace the first three DLCs or describe the commercial agent track.

## Why move inside the model?

The first four stages keep original memories outside the model, use an FSM to retrieve and execute, and let a logic pool follow separate event chains. The first three DLCs add short-term working copies, controlled index maps, and the reuse of process fragments through concrete or abstract indices. Those mechanisms make some knowledge and processes traceable, but they are still external to the model. A Transformer's behavior depends on the combination of weights, context and activations. An output or activation difference does not by itself identify logic that can be reused elsewhere. Rather than making a complete reverse engineering of an existing model a prerequisite, we propose building a representation that can be recorded, translated and tested.

## DNA and proteins: two software representations

| Software analogy | Corresponds to | Meaning |
| --- | --- | --- |
| **DNA** | **Abstract mapping relationships** | Preserve under which conditions one representation or state can lead to another, and where a relationship stops being reusable. Memory records can supply distinct, sourced instances for identifying a shared relationship. Sharing a relationship does not make the instances interchangeable. |
| **Protein** | **Concrete logic** | Bind a relationship to the current objects, conditions, resources and evidence to produce a concrete executable path. The FSM carries executable steps and checks their outcomes. Issuing a request is distinct from confirming its effect. |

A **translator** would turn an abstract relationship into executable logic for the current context, while preserving the provenance and scope of the composition. Concrete experience can return as new evidence, but an execution result does not directly rewrite an abstract relationship. Which experiences justify revision, how mappings are learned and translated, and which paths can be reused are open experimental questions. DNA and protein are software analogies, not proposed biological mechanisms or claims that existing model weights can be losslessly decoded.

An event chain can be a minimal carrier for a traceable transformation. The goal is to move it into the model's representations rather than simply add more external tools, while keeping connectionist adaptation to context. One engineering direction is to split semantics into traceable relationships and use a connectionist component to compose them again. Recompute the affected parts after an edit; do not assume local recomputation is sufficient when the dependency boundary is unknown.

## A first falsifiable experiment

1. Collect sourced evidence for the same candidate relationship in two different concrete situations.
2. In a held-out third situation, retrieve the candidate with an abstract index and rebind its objects. Use paraphrases as positive cases and changed prerequisites or reversed roles as negative cases.
3. Compare full recomputation and incremental updates. Record output agreement, changes to unrelated chains, which nodes were actually recomputed, and whether unsupported cases are rejected. If the relationship does not transfer, or incremental updates break unrelated semantics, the trial fails.

The first three DLCs have independent synthetic prototypes. Learning, translation and incremental model computation are designs to test, not capabilities claimed by this release.
