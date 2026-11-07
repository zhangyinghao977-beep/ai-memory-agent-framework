# The empiricist proposal and current concepts

[中文](DESIGN.md) | [English](DESIGN.en.md)

This page is a technical digest, not a newly ratified specification. The core design is based on the 2026-10-22 design draft; conceptual updates follow glossary v0.57 dated 2026-11-02. The latter records design intent and working agreements, which do not themselves establish implementation or experimental success.

## Current clarification: 2026-11-07

The [learning/work event-chain and cache-integration workflows](../../docs/ARCHITECTURE_FLOWS.en.md) supplement this page. The **learning event chain is EA**; it and the work event chain cover formation and use respectively, like the learning and work forests. Earlier descriptions of within-chain relational attention remain mechanism descriptions, not grounds for rejecting the current name. A particular experimental EA module is not thereby promoted to a complete implementation of the learning event chain.

Practical tool results first enter the cache with their original occurrence records retained. During rest, another part of the same FSM coordinates integration, and the learning side organizes knowledge revisions. Caching does not certify content as true, and one result must not directly overwrite existing knowledge. Summaries do not replace original memory; revisable knowledge relations and retained original text have distinct roles. Integrating experiences is different from structurally merging a subchain into the analysis scope.

Awake, mind-wandering, and sleep are individual states. Awake integration is more restrained because current activities matter. Mind-wandering has no current task or purpose and is not assigned a mandatory housekeeping role. Sleep permits more aggressive integration but neither guarantees nor mandates global optimization on every occasion. Triggers, transitions, and integration criteria still require concrete design.

Active search takes priority at this stage. The former passive-first plan is retained as history without permanently excluding passive supply. Full empiricism still means logic, memory store, and FSM operating together; a slice missing part of that system cannot validate the complete form. Numbers may describe differences, causes, phenomena, and costs, but a single score does not replace those judgments. Historical plans, predictions, failures, and frozen records are not rewritten.

## Knowledge carriers and the three question facets

What concerns knowledge and its organization; why concerns connection computation and generalized functional mapping rules; how concerns practice, tools, and event-chain organization. These facets can be transformed into one another, but each transformation still needs explicit inputs, operations, outputs, and feedback. Arrows in a diagram cannot substitute for algorithms.

Knowledge is divided into memory knowledge and abstract knowledge. Memory knowledge includes permanent/long-term memory knowledge and cached memory knowledge. Unfinished subchains, concrete progress, and intermediate products can belong to cached memory knowledge. Long-term retention does not imply abstraction, and the presence of a cached record does not imply that its content has been verified. The learning-material repository on the why side has a separate training-material role; not all memory should be relabeled as learning material.

The central knowledge carrier holds material, combination packages, participation bindings, versions, relationships, and experiential provenance. In this project, knowledge package and index package are two names for the same object, not two separate entities. Original material and source identities remain traceable; structural and representational revisions are carried by new versions. Stable identity does not mean that all neural parameters are frozen.

The first member placed in a package establishes its fixed reference. That reference is not selected anew for each query during the package's lifetime. The package's identity remains distinct from the reference member's identity. Transformations between references may be investigated, but cannot be assumed to exist universally, be reversible, or be lossless. Deviations under different references cannot simply be added. When no earlier distinguishable reference exists, the object itself is the zero-deviation reference and tracing terminates. Zero does not mean unknown, nor does it mean that all roots are the same object.

## The two forests and commonality with differences

The learning forest forms combinations from the bottom up; the working forest unfolds existing combinations in the reverse direction. Learning includes continued combination, refinement, and reuse within a layer, rather than automatically advancing a layer on every iteration. Newly formed lower-layer packages must genuinely become material for higher layers; each layer must not simply return to and re-encode the original corpus. Physical storage may share a DAG, but shared material does not imply identical concepts or participation relationships.

Finding commonality first produces a shared structure and a provisional package, within which differences are then retained. Those differences must participate in actual selection, transformation, or unfolding, rather than merely being logged. For example, “I eat apples” and “you eat pears” may organize distinct subject and object bindings around a shared symbol and propose the new combination “I eat pears.” Not having seen the whole sentence in training is not an automatic reason to reject it; structural combinability does not establish that the event occurred in the world.

New experience initially retains its local working scope and provenance, rather than directly overwriting global combinations. Derivations, exploratory proposals, observations, and practical outcomes must be distinguished. The occurrence of an action does not automatically prove a derivation correct. Revisions of concrete content are organized through the learning layer into new versions, retaining old knowledge and evidence of original experiences.

## Bootstrapping and substitution-driven revision

The bootstrapping direction is tokenization, or initial whitespace splitting for suitable writing systems, followed by candidate fragments, minimal combinations and provisional slots, substitution checks, and structural revision. Tokenization supplies candidate boundaries only; it cannot stand in for semantic roles or complete structural binding. Initial linguistic slots provide a starting point and later extend to broader process positions and relationships. Not every causal or code structure should be forced back into grammatical constituent slots.

Substitution checks need executable grounds, such as explicit source bindings, defined structural compatibility constraints, independent held-out material, or practical feedback. Failures should be traced to boundaries, slots, bindings, or context, then retested using new versions. Missing matching evidence should remain unknown rather than generating invented negative examples. A generator's own score cannot be the sole judge.

The 2026-10-22 draft proposes candidate implementations involving Q/K/V, a soft structural bias B, and conditional FFNs. Relationship weights are not knowledge content, and per-candidate outputs do not automatically form knowledge packages. Member sets, structural binding, and registration interfaces still need to be specified. Unknown relationships are not automatically hard-masked merely because a grammatical edge is absent; genuinely invisible content is subject to the appropriate masking. Candidate designs must be compared with alternatives such as no structural bias, without presuming superiority.

## Event chains and hierarchical collaboration

In the original empiricist discussion, event chains encompass generalized ASTs, knowledge combination, and transformations among the three question facets. The nine cells describe transformation responsibilities, not a fixed nine-step pipeline. Knowledge combination and event chains have an established relationship, and a chain can itself be knowledge. Distinguishing an abstract structure from the state of a particular execution does not require forcing them into mutually exclusive storage systems.

Main-chain and subchain roles are relative to task scope. Subchains collaborate through protocols defining inputs, result interpretation, and errors. Their how outlets can be used by consumers meeting the relevant reading conditions. This describes architectural responsibilities and grants no external sharing permission. Main chains and subchains have invocation and feedback relationships but do not share loss; this does not make their actual resource consumption zero.

A single looping subchain can execute multiple rounds, sharing one finite resource pool for that loop rather than unconditionally resetting the budget each round. Package-based organization delegates within-package tasks to lower-level subchains, whose local products then participate in higher-level processing. Backtracking can support rerouting and tracing, but cannot undo actions that have already changed the real environment.

Concrete progress, unfinished subchains, intermediate products, and blocked attempts need a way to be retained. Chained caches, separating shared structures from instance state, and saving state before releasing active resources are engineering directions. Tensor layouts, fields, recovery protocols, retention periods, and eviction mechanisms remain undecided. Suspension is not task completion, and recording does not guarantee lossless recovery.

## Divide-and-conquer streaming and exploration boundaries

The later v0.55 clarification makes divide-and-conquer streaming from startup a core training requirement: work cycles between CPU/local storage and GPU, with very small neural computation units participating. This is not an optimization added after training, nor is it equivalent to dividing a single large network's workload into mini-batches. The requirement does not automatically prescribe one network per package, a fixed parameter count, a disk write at every step, or unloading all weights every round.

When conditions change, the direction is to retain valid parts and revise affected content along dependencies. If the impact extends beyond a local scope, that scope may expand. An effective local repair is not automatically the least-cost repair. The best result found in a finite search is not necessarily a local or global optimum, and this provides no P/NP classification or proof.

Versions v0.56 and v0.57 further clarify that curiosity may motivate exploration of better solutions, without requiring endless optimization or using exploratory achievement to establish worth. When a solution is effective and sufficient under finite conditions, exploration may stop or pause. Awake/sleep states offer different resource and reorganization opportunities, not a guarantee of finding a global optimum.

## Work still requiring implementation and validation

Key gaps include the structural binding operator, substitution criteria, coordination of discrete revision with training losses, actual cross-layer inputs, reverse unfolding, version dependencies, resource accounting, and recovery interfaces. Subsequent training must not read evaluation targets back through derived slots, caches, summaries, or deviation records. Continued learning after accessing evaluation feedback must be reported separately as online adaptation.

Suggested checks separately cover legitimate new combinations, illegal bindings, preservation of unknowns, segmentation revision, the actual effect of lower-layer version changes on higher layers, local/global isolation, and source tracing. Measurements should also cover recall, leakage, candidate scale, fan-out, latency, and memory rather than only success rates. These are design requirements and a proposed validation route, not new experimental results from this compilation.
