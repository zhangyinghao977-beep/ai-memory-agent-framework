# Hongchenxian and Claude: from remembering progress to resuming execution

[简体中文](CLAUDE_ARCHITECTURE_COMPARISON_20261127.zh.md) · [Public prototype](https://github.com/zhangyinghao977-beep/hongchenxian-prototype)

This note compares public documentation as of November 27, 2026. It does not infer Claude's internals or rank model capabilities or product maturity. The main comparison is Claude Managed Agents; Claude Code features are labeled separately. Hongchenxian is a standalone agent research prototype. Stage 5 is a separate research agenda for the AI architecture itself.

## 1. Division of responsibilities

[Anthropic's Managed Agents architecture](https://www.anthropic.com/research/managed-agents) separates session events, the harness that calls the model and routes tool calls, and the execution environment. [Dynamic workflows](https://platform.claude.com/docs/en/managed-agents/workflow-runs) also let an agent write programs that coordinate multiple agents in phases. Both designs put some execution and coordination outside a single model response. Hongchenxian starts from three questions: What do we know, and from which source (memory)? Why choose a path (reasoning)? How do we execute it (the state machine, or FSM)? An event chain records transitions among these questions and maintains a separate point of progress for each running path. It is not just a transcript or a diagram drawn after the fact.

## 2. Memory: what can be read and what can change

[Claude Code auto memory](https://code.claude.com/docs/en/memory) retains lessons and corrections as editable notes for later context. [Managed Agents Dreams](https://platform.claude.com/docs/en/managed-agents/dreams) can also review past sessions and create a separate memory output for review without changing the input store. Hongchenxian likewise separates working material from the trusted source, with a specific split between original records, keyword indexes and revisions. A short-term workspace reconstructs only the relevant material; its edits stay isolated unless explicitly merged back as patches. Where access must be scoped, callers see only an approved index map rather than the trusted source directly. These are separate prototype demonstrations, not a ranking of isolation guarantees.

## 3. How: when is a process worth turning into a reflex?

[Claude Code Skills](https://code.claude.com/docs/en/skills) can supply task instructions and supporting scripts; [Hooks](https://code.claude.com/docs/en/hooks#pretooluse) can run code in response to events or block a tool call. Claude has programmatic execution controls as well as instructions. In Hongchenxian, a guide or subguide packages a process **because it is already controllable**; packaging does not make it controllable. A conditioned reflex is a kind of How: once its trigger is registered, the FSM can call existing tools and check the result without asking the model to reason it through each time. A reflex can itself be interrupted by another reflex. The event chain can temporarily record where it stopped and which effects are not yet confirmed.

## 4. Resumption: issuing an action is not confirming its effect

Anthropic's [long-running agent example](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents) uses progress files, Git and environment checks to hand off work. The Managed Agents [event reference](https://platform.claude.com/docs/en/managed-agents/reference) distinguishes tool calls from tool results. The useful comparison is **what state survives a particular interruption and what evidence allows the run to resume**, not a claim that Claude cannot resume.

In a separate offline simulation, a dismissible prompt interrupted a mock form after submission but before its result returned. The version that kept the original pending action issued one request and waited for its matched result. The restart control deliberately discarded that state and issued two requests. This was not a comparison against Claude. It did not use real websites or accounts, test recovery after a process crash, or test multiple concurrent interruptions. [DLC 03](https://github.com/zhangyinghao977-beep/hongchenxian-prototype/tree/main/dlc03) demonstrates the underlying event-chain and reflex primitives; the nested test itself is not part of that public prototype.

## 5. Stage 5: learning executable logic from experience

[Stage 5](../projects/hongchenxian/demo/STAGE5.en.md) asks whether a system can learn an abstract mapping and its boundaries from multiple sourced experiences, then bind that mapping to the current objects and evidence to form a concrete executable path. The project's DNA/protein analogy refers to these two software representations. One execution result does not overwrite the abstract mapping. This is unimplemented research, not a new name for auto memory or a claim to have extracted the logic of an existing Transformer.

**Feedback welcome:** Give both setups the same tool, permissions, and interruption point. Let the tool receive a request, delay the result, then interrupt the run. Which layer keeps the pending action? What evidence permits resumption, and when should the run stop? If a documented combination of Skills, Hooks or Managed Agents already covers the case, a minimal setup would give us something concrete to compare and rerun.
