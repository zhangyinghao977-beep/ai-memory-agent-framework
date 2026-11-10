# FSM: current state, future continuity and event chains

[中文](FSM_CONTINUITY.md) · [Glossary](GLOSSARY.en.md) · [Architecture flows](ARCHITECTURE_FLOWS.en.md)

Updated 2026-11-10. U-FSM-1110 adds subsequent takeover and recording boundaries. Original source U-FSM-1109: technical paraphrases of explicit author confirmations in the discussion with the assistant. These are design definitions, not completed implementation, successful tests, or evidence of current AI subjective experience. Historical experiments remain unchanged.

## 1. Responsibilities and integration

**Memory belongs to the past, logic to the present, and the FSM to the future.** This project classification does not describe three disconnected boxes. Logic, memory and the FSM must remain connected in operation. Engineering can proceed in modules, but local experiments do not validate the complete system.

Logic is the “brain”; the FSM is the “body/tool.” The FSM does not understand tasks, relate experiences or decide goals. It can nevertheless execute purely symbolic decisions: if/else, threshold comparisons, explicit rules and state transitions. “Does not understand” must not become “cannot evaluate any condition.” Logic uses memory to decide which task a resource change concerns and whether to continue; the FSM need not know that relationship itself.

Besides future continuity, the FSM must interact with current physical state, resources and continued operation. This does not change its classification as future-facing or transfer present understanding away from logic.

## 2. Resource protection and reserved capacity

The resource pool refers to actual physical/computational resources. Specific protection conditions may adapt through experience but cannot exceed physical limits. Adjustable protection conditions do not make actual capacity arbitrary.

Default protection reserves capacity to record memory instead of waiting for exhaustion; section 6 describes the specific logic-takeover exception. The existing fixed-protocol requirement to save memory before reporting remains. This discussion does not prescribe a fixed reserve, measurement method or validated protection mechanism.

Ordinary fluctuations need not interrupt logic each time. An allocated working part that remains within its preset range can be left alone; exceeding that range requires attention. This does not mean deleting memories, disabling necessary state observation or assigning one threshold to all tasks.

## 3. Symbolic exception routing

- **Low risk: report first; logic decides.** The executing step may continue or pause depending on the case; no universal policy is imposed. Concrete conditions for increasing risk still need design and testing.
- **High risk: interrupt the current task, preserve complete memory, then report and wake logic.** This default protection can execute through symbolic rules without waiting for logic to understand the cause. A sleeping or inactive logic is woken directly rather than waiting for natural awakening.

A complete record preserves the reason, progress, process and context, not merely a short status marker. “Cut off” does not by default mean terminating the entire process or machine. The FSM saves original records and registers fixed fields such as time, result and the current event chain. **Logic determines indexes and descriptions**; the FSM does not understand content to generate them. Logic subsequently processes the records and decides next actions.

Default protection preserves recording reserves and saves before reporting. Persistence, completeness and recovery under actual failure conditions still require engineering validation. This does not supply a tested memory-leak detector. The specific logic-takeover exception is described in section 6.

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

## 6. In-flight adjustment and specific logic takeover

Ordinary budget or rule changes must account for resources already spent and current progress; a new rule does not uniformly cancel in-flight work. Default high-risk protection acts directly without waiting for deliberation. Reflexes are an explanatory analogy, not biological equivalence or implementation evidence.

The author also allows **logic to take over in specific circumstances, accept danger and force execution**. This may use all available resources, including memory-recording reserves, accepting the risk of incomplete records. Objective physical capacity cannot be exceeded. This research definition is not permission to bypass external authorization or deployment safety constraints.

For termination of takeover, the author specifies “resource exhaustion + logic giving up,” explicitly meaning **both**, not either. Logic judges whether the event has ended; completion of one step does not automatically return control. How logic could still judge or execute after actual resource exhaustion remains an unverified engineering issue, not an established executable termination protocol.

**The temporary large memory store is an untested hypothesis.** During takeover, logic may set aside other possibilities and concentrate computation and storage on a local capability for the current task, attempting to convert available costs into execution resources. The author explicitly states that this has not yet been tested in a real experiment. No performance gain or guaranteed completion is claimed.

## 7. Remaining work

Responsibilities, symbolic evaluation, range checks, high-risk interruption of the current task with complete recording and wake-up, logic-generated indexes/descriptions, and case-specific low-risk handling are confirmed rather than wholly undefined.

Remaining work includes concrete step ranges and risk conditions; reliable leak detection; measurement of recording reserves; symbolic low-risk routing rules; interfaces between cache, original records and logic completion; exact application of rule changes to in-flight actions; executable takeover/exhaustion semantics; and experiments on the temporary large memory store. New definitions do not overwrite original facts, failures or historical results.
