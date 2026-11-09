# FSM: current state, future continuity and event chains

[中文](FSM_CONTINUITY.md) · [Glossary](GLOSSARY.en.md) · [Architecture flows](ARCHITECTURE_FLOWS.en.md)

Recorded 2026-11-09. Source U-FSM-1109: technical paraphrases of explicit author confirmations in the discussion with the assistant. These are design definitions, not completed implementation, successful tests, or evidence of current AI subjective experience. Historical experiments remain unchanged.

## 1. Responsibilities and integration

**Memory belongs to the past, logic to the present, and the FSM to the future.** This project classification does not describe three disconnected boxes. Logic, memory and the FSM must remain connected in operation. Engineering can proceed in modules, but local experiments do not validate the complete system.

Logic is the “brain”; the FSM is the “body/tool.” The FSM does not understand tasks, relate experiences or decide goals. It can nevertheless execute purely symbolic decisions: if/else, threshold comparisons, explicit rules and state transitions. “Does not understand” must not become “cannot evaluate any condition.” Logic uses memory to decide which task a resource change concerns and whether to continue; the FSM need not know that relationship itself.

Besides future continuity, the FSM must interact with current physical state, resources and continued operation. This does not change its classification as future-facing or transfer present understanding away from logic.

## 2. Resource protection and reserved capacity

The resource pool refers to actual physical/computational resources. Specific protection conditions may adapt through experience but cannot exceed physical limits. Adjustable protection conditions do not make actual capacity arbitrary.

Protection must reserve enough capacity to record memory instead of waiting for exhaustion. The existing fixed-protocol requirement to save memory before reporting remains. This discussion does not prescribe a fixed reserve, measurement method or validated protection mechanism.

Ordinary fluctuations need not interrupt logic each time. An allocated working part that remains within its preset range can be left alone; exceeding that range requires attention. This does not mean deleting memories, disabling necessary state observation or assigning one threshold to all tasks.

## 3. Symbolic exception handling

- **Low risk: report first and let logic decide.** No universal continue-or-pause behavior after reporting was specified.
- **High risk: cut off first, then report.** For a clearly established problem requiring termination, such as a confirmed memory leak, the FSM may terminate according to rules without first requiring logic to understand the cause.

Explicit symbolic conditions may classify the risk. Not every range exceedance requires immediate termination, and not every exception must wait for logic. This is not an implemented memory-leak detection algorithm.

Preserve both “cut off before reporting” for high risk and “reserve capacity; save memory before reporting.” The cutoff scope and exact ordering of cutoff, memory preservation and reporting still need implementation detail. Do not infer a whole-machine power-off or shutdown of the memory-recording capability.

## 4. Event-chain steps and unfinished work

Checking the allocated working part against a preset range requires the event-chain capability to decompose a task into n steps; otherwise the task can become blocked as one opaque whole. No fixed n, granularity or universal budget is prescribed.

Cache and memory can record partially completed tasks, preserving the process and progress for later continuity. Logic decides whether to resume or adjust. Preservation does not require the FSM to understand a task, nor does restored capacity force automatic resumption.

**The empiricist architecture and the agent slice use the same event-chain concept.** The agent slice does not need to carry its learning integration because it cannot integrate it into the existing logic layer; the empiricist design includes event chains in the complete learning architecture. Distinguish coverage and integration scope, not unrelated concepts. Shared concepts do not imply identical implementations or complete learning in the slice.

## 5. Models, agents and the full architecture

These are the author's project categories, not established schools:

1. Strict traditional: the Transformer-based LLM itself.
2. Improved/broad traditional: an agent framework based on such an LLM.
3. Compromise: that agent framework supplemented with this project's memory store and FSM.
4. Empiricist: a rebuilt complete AI architecture with its own memory store and FSM.

The initial conception moved directly from the traditional model to the empiricist architecture, leaving intermediate layers folded away. Difficulty implementing the whole led to a compromise slice compared with improved agents. The slice is not the original final goal or proof that the complete empiricist design is implemented. Comparisons must distinguish a model from an external framework and a complete system.

## 6. Specific open details

Responsibilities, symbolic evaluation, experience-adjustable protection within physical limits, range checks, low-risk reporting/high-risk cutoff, and event-chain decomposition are confirmed. Do not label those entire capabilities undefined.

Open details include concrete per-step ranges and risk conditions; reliable identification of faults such as memory leaks; execution while a low-risk report awaits a decision; cutoff scope and memory preservation; detailed cache/memory recording interfaces; and how condition changes affect in-flight actions. These are open design or engineering questions, not author-approved protocols.
