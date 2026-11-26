# Event chains: pause, handle the interruption, and resume

[简体中文](EVENT_CHAIN_REFLEX_20261126.zh.md) · [Earlier FSM notes](FSM_CONTINUITY.en.md) · [Public Hongchenxian prototype](https://github.com/zhangyinghao977-beep/hongchenxian-prototype)

## An everyday example

Say you open a browser to read a page and a prompt asks to make it the default browser. You can dismiss that prompt and continue to the page you wanted without reopening the browser. This illustrates the design; it is not a browser test result.

An event chain describes transitions between what, why, and how. It also gives a running task somewhere concrete to pause: the browser is open, but the target page is not. If an interruption matches a registered condition, the task pauses and the finite-state machine (FSM) temporarily takes over to run the conditioned reflex. Once it confirms the interruption is clear, it hands control back to the original checkpoint. The LLM does not have to make that decision again when the reflex fires. If the condition does not match, the outcome cannot be confirmed, or a step requires new permission, the decision returns to the reasoning layer, which can ask the user when needed.

This narrow resume path preserves the separate [FSM rules](FSM_CONTINUITY.en.md) for high-risk stops and exceptions that need a fresh decision.

## Local observation: Day 12 in Lobotomy Corporation

In one local run, the interface indicated suppression was underway, but that did not establish that the team was in position. A later run checked whether the danger had stopped and whether the team was in position separately before continuing. This illustrates why a reflex needs to check the actual state rather than rely on a status label. The runs were not a controlled comparison, so the successful run cannot be attributed to one mechanism. No raw footage or logs are included.

## What runs now and what comes next

- **Standalone Agent:** [DLC 03](https://github.com/zhangyinghao977-beep/hongchenxian-prototype/tree/main/dlc03) uses synthetic inputs to demonstrate event chains, the FSM protocol, and reflexes. In-flight state is demonstrated only within a running process; this does not establish crash recovery. In the Agent design, a separate LLM judges unfamiliar situations and decides whether to register a new reflex. The FSM executes registered rules.
- **Stage 5 / Empiricist AI:** The [Stage 5 design](../projects/hongchenxian/demo/STAGE5.en.md) aims to combine the LLM and Agent into one system that learns reusable logic from its own experience and applies it in action. Event chains would carry logic transitions previously left implicit inside the Transformer. The goal is neither to remove the entire Transformer nor to extract a ready-made rulebook from its weights after training. The integration and learning mechanism are not implemented.
