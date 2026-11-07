# Architecture flows: formation, use and active retrieval

[中文](ARCHITECTURE_FLOWS.md) · [Glossary](GLOSSARY.en.md) · [Logic, memory and FSM principles](MEMORY_LOGIC_FSM_PRINCIPLES.md)

Updated: 2026-11-07. Sources: U-1107 and C58 (see the [source register](GLOSSARY_SOURCES.json)) and the public designs below. These are public comparison views of the current discussion, not a newly frozen specification or experimental result. This update does not claim a review of every diagram on the earlier site. Frozen plans, historical scores and failure records remain unchanged.

## 1. Forming experience-based knowledge and using it in work

![Formation and use design](diagrams/formation-use.en.svg)

[Editable DOT source](diagrams/formation-use.en.dot)

Arrows describe design responsibilities and feedback directions, not completed operators, interfaces or scheduling algorithms. Learning and work are the **formation and use sides**, without requiring mutually exclusive databases or two separate FSMs.

- Tool-practice results enter the cache first, preserving raw occurrence records and source types. Recording a guess, plan or error does not turn it into a verified fact.
- At rest, **another part of the same FSM** schedules integration of cached experiences. Learning event chains (EA) / the learning forest form or revise knowledge and memory; work event chains / the work forest use existing knowledge, unfold it and call tools. The loop does not require completed learning immediately after every tool call.
- Awake activity is more restrained. Mind-wandering has no task or purpose and is not assigned fixed background duties. Sleep can support more aggressive integration, without guaranteeing local or global optimality. The state annotation is not a complete transition table.
- Raw records, interpretations formed through learning and knowledge versions remain distinguishable. Briefs or relation representations cannot replace memory originals; revisions preserve earlier evidence.

This view confirms EA as learning event chains without inventing an English expansion of the acronym or inserting CA into the meaning of historical diagram 01. Integration operators, scheduling triggers, admission criteria, resource allocation, retention and recovery protocols remain to be specified. No new R algorithm is introduced. If R is added later, its feedback into knowledge, chains, memory admission and the FSM must be made explicit rather than drawing a score box with no defined effect.

## 2. Agent: active retrieval first and phase-two local attention

![Active retrieval and local attention](diagrams/active-retrieval.en.svg)

[Editable DOT source](diagrams/active-retrieval.en.dot)

**Active retrieval is the current priority.** This replaces the earlier passive-first staging, without permanently abandoning passive retrieval. Logic actively consults the index dictionary and selects entry points layer by layer; indexes may themselves be indexed. Briefs introduce material from the corresponding index perspective. Logic decides whether to expand originals, which ones to read and whether the evidence is sufficient.

The **phase-two design** provides the target original, related upper/lower index briefs and expandable references together. Index relationships can involve hierarchy and association; they are not merely physical preceding/following paragraphs. Missing conditions, unclear references, conflicting material or questionable briefs call for reading the relevant originals. No match and exhausted budgets do not prove absence. Summaries do not replace originals; tool results still enter the cache before integration.

**Observed implementation and gaps:** the public RecallAdapter exposes components including `readIndex`, `previewIndex` and `readOriginal`; `readOriginal` currently fixes `neighborMode: 'raw'`. The lower-level `readParagraphWindow` supports `summary-preferred` for physical neighboring paragraphs only: the target stays original, and neighbors fall back to originals when no brief exists. This is not the full index-relationship policy. The complete phase-two combination, relevance and sufficiency judgments are not yet connected and validated. The dashed yellow box marks phase-two design; the green note marks component capabilities only. Other nodes remain responsibility descriptions, not evidence of end-to-end completion.

## 3. Two senses of merging and the scope of complete validation

“Connecting a subchain into a structure” and “integrating cached experiences” are explanatory qualifiers to avoid ambiguity, not two newly coined formal terms:

- **Connecting a subchain into a structure:** connect main chains and subchains through input, result-interpretation and error protocols, preserving calls, feedback and version relationships. Structural connection does not imply that experience has been absorbed as knowledge.
- **Integrating cached experiences:** decompose, organize, relate or revise retained experiences to form knowledge and memory for later use. Raw records are not disposable drafts overwritten by the latest interpretation.

The complete empiricist proposal includes **logic + memory + FSM**, whose interaction requires whole-system validation. Comparisons must distinguish three approaches: **traditional (traditional Transformers and traditional agents), compromise (the author's agent slice), and empiricist (logic, memory store, and FSM in their complete form)**. Identify concrete implementations and coverage in each approach rather than treating traditional agents and this project's slice as the same proposal. Agents borrow capabilities of their underlying models, so slice success does not establish the complete architecture.

State the models, materials, visible information, budgets, versions and task differences. Compare accuracy, reliability, resistance to contamination, speed and honest preservation of unknowns separately rather than hiding trade-offs in one score. Offline doubles, synthetic identities, correct storage and source checks support only their tested scope. They do not establish complete learning, original-identity recovery, real multi-member collaboration or long-term continuous operation. This update adds documentation and diagrams, not new learning experiments.

## 4. Public sources and reproduction

- [The Abyss design](../projects/the-abyss/DESIGN.en.md): dual forests, knowledge composition, feedback and resource boundaries.
- [Hongchenxian architecture](../projects/hongchenxian/docs/ARCHITECTURE.en.md): retrieval interfaces and offline evidence scope.
- [Logic, memory and FSM principles](MEMORY_LOGIC_FSM_PRINCIPLES.md): observed components and source-code links.
- [Glossary](GLOSSARY.en.md): current definitions, evolution and unresolved items. Explicit newer corrections take precedence over conflicting historical wording without deleting it.

The diagrams are generated from Graphviz DOT with Noto Sans CJK SC and use no online assets. Run from the repository root:

```sh
for f in docs/diagrams/*.dot; do
  dot -Tsvg "$f" -o "${f%.dot}.svg"
done
```

For visual checking, use e.g. `dot -Tpng docs/diagrams/formation-use.en.dot -o /tmp/formation-use.en.png`; PNG files need not be committed. Graphviz and font versions can affect layout. These two bilingual diagram pairs are public comparison views, not replacements for unlisted old diagrams or frozen architecture records.
