# Architecture scope of this preview

[简体中文](ARCHITECTURE.md)

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
