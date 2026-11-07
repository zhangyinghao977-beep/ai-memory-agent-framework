# Architecture scope of this preview

[简体中文](ARCHITECTURE.md)

## Current design: active search and phase-two local attention

The current choice, confirmed on 2026-11-07, is **active memory search first**. Logic actively chooses its first entry from an index dictionary, follows further index levels when needed, reads summaries from the respective index perspectives, and decides whether to unfold original text. An index may itself be indexed. Time, place, person, tool, object, and result are example entry points for an experience, not a mandatory six-field schema for all memory.

**Local attention is a phase-two design, now documented alongside this flow.** The target original text should arrive with related upper/lower-index summaries and references that can be unfolded. Those relations may be hierarchical or associative, not just the immediately preceding and following paragraphs. Summaries follow their indexes; different entry points may provide different summaries of the same original. Summaries, integration, and read budgets do not authorize compressing, overwriting, or deleting that original. Logic retains judgment; FSM and memory support states and materials rather than take over the decision.

Tool results first enter the cache with their original occurrence records retained. A result having been returned is distinct from its content being true. During rest, another part of the same FSM coordinates integration of cached experiences. This differs from structural merging that brings a subchain into the current analysis scope. These qualifiers explain the distinction rather than name new operators. Triggers, admission criteria, and complete protocols remain open; the offline collaboration path does not establish autonomous integration.

**Historical change:** The earlier passive-first plan is superseded by active-first at the present stage. Passive supply means providing materials before logic requests retrieval. Its meaning and history are retained; whether, when, and how it will accompany active search remain open. It has not been permanently abolished.

See the matching [bilingual workflows and design/implementation comparison](../../../docs/ARCHITECTURE_FLOWS.en.md) and [current glossary](../../../docs/GLOSSARY.en.md). The full empiricist evaluation concerns logic, memory, and FSM together. Agent slices and offline protocol checks do not validate that complete form.

**Implementation boundary:** The underlying `summary-preferred` window and the native `readOriginal` path must be described separately. `readOriginal` currently fixes `neighborMode: 'raw'`; the underlying summary option covers neighboring paragraphs, not all related upper/lower indexes. The complete phase-two composition and its end-to-end behavior are not established.

## Data and execution path

A synthetic claim binds a member, session, policy, and ticket. Memory references carry only fixed snapshots/pins. Tools search the index, inspect a preview, and then retrieve selected original text. Native-tool source records must match their results. A tool return does not automatically become a member's final opinion or lifecycle decision.

`runCentralPlugin` registers a provider and stream hook in the local double. Each step first obtains admission. The protected transport then checks the actual serialized request, durably records spend, and passes it to an injected offline forward function. Completed source, Body acceptance, receipt, settlement, and opinion staging remain distinct records.

Reopening first verifies retained source and accounting records. Only complete, consistent evidence of a completed source permits filling in missing local records for the same ticket. Unknown, conflicting, foreign, or incomplete evidence remains held. A later decision cannot be written back as an earlier request's success. An exception alone never justifies another provider call.

## Important boundaries

- `sdk-runtime-double.mjs` is a controlled model, not the installed official runtime.
- Tests contain ten synthetic identities, but the actual execution path covers one member, not ten-member concurrency or a collective meeting.
- Source hashes and lineage checks are not cryptographic identity authentication or host-level writer exclusion.
- Temporary SQLite persistence and simulated session reopen are not proof of cross-process, power-loss, or real-server recovery.
- Read budgets and window limits are not permission to delete history or forget automatically.
- The official loader in this preview always refuses. Production integration, original-identity migration, and 72-hour operation are out of scope.

`syntheticOnly` and `officialRuntimeExecuted` describe the fixed offline composition. They do not authenticate arbitrary SDK/deps injected by a caller. Direct module reuse requires separate constraints on dependencies, permissions, and network access.
