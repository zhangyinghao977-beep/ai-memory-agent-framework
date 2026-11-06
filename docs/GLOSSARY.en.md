# Project glossary: consolidated coverage

[中文](GLOSSARY.md) · [Repository](../README.en.md) · [Sources and versions](GLOSSARY_SOURCES.json)

**Navigation:** [Event chains](#event-chains) · [Core concepts](#core-terms) · [Implementation crosswalk](#implementation-terms) · [Sources](#sources) · [Meeting agenda](#meeting-agenda)

**Compilation 2026-11-07-r1: a discussion snapshot, not a newly ratified specification.** This document combines the existing glossary, later clarifications and operational meanings in code. It can be read from the beginning without following earlier supplements. It does not replace the author's version numbering or derive theoretical definitions from implementation shortcuts. “Complete” means coverage of the main concepts and cross-project ambiguities in the inspected sources, not that every mechanism has been specified.

The Abyss is an unfinished empiricist AI research proposal involving memory, knowledge organization, paths and learning. Hongchenxian studies memory and work coordination for black-box agents. These are **project-specific terms**. Adopting a definition, implementing an interface and obtaining experimental support are different states.

## Reading conventions

Entries distinguish **author definitions / working agreements**, **operational meanings** and **open questions**. English names are editorial translations. Acronyms such as KA, EA, PA and CA are not given invented expansions. `D54:345` refers to line 345 of source D54; source identifiers are listed at the end. Private quotations, complete conversations, accounts and absolute local paths are excluded.

Precedence is not simply the last paragraph or newest file timestamp. An explicit correction takes precedence over the statement it replaces; code establishes what was implemented, not what the author must mean. The latest R26 document records three correction rounds but retains contradictory older conclusions at its end. This glossary preserves that evolution and **does not treat the superseded ending as the current definition**. R26 is a researcher's record of user-confirmed terminology; the complete underlying conversation was not independently reauthenticated for this compilation. Remaining ambiguities stay explicit.

<a id="event-chains"></a>

## Event chains: identify the level first

| Usage | Meaning | What it does not establish |
|---|---|---|
| Generalized event chain in The Abyss | Organization of knowledge composition, operations and relations, expressed through generalized AST structures and paths among what / why / how | More than a chronological log; the name AST does not supply complete execution semantics |
| Occurrence / execution instance | Which structure version was used, its bindings, progress, results and evidence | A record alone does not prove a real event occurred; plans, observations, execution and reports differ |
| Path memory | Reusable correspondences between concrete objects, abstract concepts and other objects | Not merely neighboring coordinates, all parameters or all chat records |
| Hongchenxian work event chain | Organization and traceability of agent tasks, roles, status, feedback, resources and handoffs | Does not inherit implementation or acceptance of The Abyss's knowledge AST or nine transformations |
| An experimental “chain” | Input defined by that experiment's generator, tensors or sample protocol | The shared name does not imply coverage of the full theory; specify what the model actually reads |

These are conceptual and operational distinctions, not a requirement for five mutually exclusive databases. A process can have a reusable structure, several occurrences and later knowledge organization, with links between them. Sources: D54:343–364,477–485; D57; R26; H0; U-AST, U-COMPOSE, U-HCX.

### E01 Event chain / generalized abstract syntax tree — 事件链／广义抽象语法树

**Author definition:** The event chain originated as an abstraction of syntax trees and was later explicitly named a generalized AST. Knowledge composition is an event chain; a chain is itself knowledge. It organizes composition, operations and relations, including nesting, folded references, unfolding and connections. It is more than an ordered list of happenings. This broader AST usage does not require the whole system to be physically stored as one conventional syntax tree.

**Operation and limits:** The registry core contains versioned structures, children and slot mappings; short chains in neural experiments have separate formats. Sharing, feedback, loops and semantic preservation require actual algorithms. Evolution: earlier syntax-tree abstraction → explicit generalized AST on October 25 → composition relationship reaffirmed October 31 → more specific interpretation of selection steps in R26. Sources: D54:22–28,345–364; A0; U-AST, U-COMPOSE; R26.

### E02 Logic / reachable path — 逻辑／可达路径

**Author definition: Logic is the path that makes knowledge reachable.** A path includes individual steps obtaining subsequent knowledge or results from current knowledge, conditions and a reference. It need not be long. A concrete door and its conditions → an abstract opening relation → a required key relation → a concrete key illustrates the concrete–abstract round trip.

**Operation and limits:** R26 permits reading one comparison-and-selection step as a what→what event-chain process. That does not establish the other eight transformations, open-world reasoning or the complete theory. Domains, constraints, unknowns and failures remain part of the path description. Sources: D54:221–245,273–287; R26:7–26.

### E03 Node — 节点

**Latest author usage:** An event-chain node denotes an operator action associated with transformations among what / why / how. A vector row is a possible engineering carrier, not the definition. R26's second correction withdraws the blanket statement that the T series has no such nodes: locating, comparing and selecting can be read as a what→what process.

**Operational differences:** The registry's `Node` is a structure object with a kind, slots and child references. T-series vector rows primarily represent objects, so each row cannot automatically be treated as a complete operator. A Hongchenxian memory paragraph may be an addressing unit, but paragraph = theoretical operator = ledger event has not been established. Unified encoding of all nine roles remains open. Sources: R26:7–26; A0; U-HCX; H0.

### E04 3×3 transformations / nine operator roles — 3×3 转换／九类算子

Each of what, why and how can map to any of the three, including itself. The nine cells describe responsibilities, not a fixed nine-step pipeline or exactly nine implemented algorithms. The core's `record_flow` records source and destination faces, inputs and outputs; recording a transition is not executing or learning it. R26 maps comparison-and-selection to what→what only. Sources: D54:359–364,507–525; A0; R26:20–26.

### E05 Path as function — 路径作为函数

This is a project modeling requirement: every path step should have an input–transformation–output function description. A drawn edge does not thereby become a specified, total or invertible mathematical function. Changing a reference resembles changing a ruler, but representation transformations and their domains must be specified. Sources: D54:273–287.

### E06 Abstract structure and instance state — 抽象结构与实例状态

A reusable structure describes positions, connections and progression. Instance state describes current bindings, progress, intermediate products and dependent versions. Bindings connect them. This allows repeated use without rewriting one structure; it does not mandate separate services or one dense tensor containing all state. Saving and recovery protocols still require design. Sources: D54:38–81; A0.

### E07 Occurrence record — 发生记录

An implementation record of an instance linked to a structure version, cache and experience or memory basis. Source types distinguish plans, execution, observation and reports. Calling `occur` or inserting a row therefore does not itself prove a real-world event. Multiple records can use one structure with different bindings, times and outcomes. Occurrence records do not exhaust the meaning of a generalized event chain. Sources: A0; D54:477–485.

### E08 Main chain / subchain and how output — 主链／子链与 how 出口

Roles depend on task scope: a subchain for an enclosing task can be the main chain for its own task. Agreed input, result interpretation and error protocols connect chains; sending a request and receiving feedback are separate steps. A how output supplies agreed content to eligible readers, not only a parent. Local completion does not finish the enclosing task or authorize external sharing. Sources: D54:118–130,453–475.

### E09 Folding / unfolding / partial decoupling — 折叠／展开／半解耦

Folding uses a registered whole or reference; unfolding enters components and subchains when needed. The main chain proceeds within its responsibility and incorporates subchain outputs while retaining provenance and feedback links: partial decoupling. Folding must not silently erase failed attempts. Reading a subtree is not evidence of semantically equivalent execution. Sources: D54:431–451,752–766,807–814; A0.

### E10 Backtracking / rollback / replay / recovery — 回溯／回滚／重放／恢复

Backtracking includes inspecting past evidence and returning to a choice point during expansion. Previous attempts and feedback remain. Rolling back computational state, replaying records and recovering after interruption are distinct capabilities requiring separate evidence. Logical reversibility does not undo real-world effects. Logs do not guarantee restoration of state, identity or computation. Sources: D54:102–108,768–805; H0.

### E11 Loop, iteration and resource pool — 循环、迭代与资源池

One looping subchain can run for several rounds; n rounds do not imply n new subchains. Rounds share a finite budget for that loop rather than refreshing it automatically. Iteration carries forward experience and valid parts while revising organization. “Loop plus iteration” emphasizes continuing accumulation across architecture changes. Resource suspension preserves unfinished status; it is not completion. Metering, replenishment and exit rules need specification. Sources: D54:110–162; D57; U-ITER.

### E12 Loss / cost / accounting — 损失／代价／账单

Earlier discussions use these terms for process and path costs; main and child chains are connected without sharing losses. State the context: this is not automatically the cross-entropy objective in code and does not remove physical subchain costs. Hongchenxian spend and settlement records are engineering accounts. Do not substitute the same word across theory, optimization and resource accounting. Sources: D54:975–983; H0.

### E13 Two current senses of memory store — 记忆库的两种当前语境

**Latest author distinction:** One store preserves an agent's work experiences. Another preserves the empiricist system's own mappings or paths: a particular key to a door, that key to the key concept, and that door to the door concept. Path memory is part of knowledge. The two can connect, but their shared name does not establish mutual implementation.

**Experimental boundary:** R26 places T13 in the first direction. A later T13 draft also proposes a frozen-weight FSM path-memory arm whose method is unsettled. The inspected T13 directory contains only an unfrozen draft, with no implementation or run receipts observed; the added arm is not a result. Current T-series object vectors and comparators do not implement the complete concrete–abstract path-memory mechanism. Sources: R26:7–16; D54:213–245; T13:72–78.

### E14 Learning, training and the “embryonic stage” — 学习、训练与“胚胎阶段”

**Latest restricted definition:** R26's third correction calls simple-FSM recording into memory after system startup “learning” in the human-like sense under discussion, and places gradient training in pre-startup initialization or the “embryonic stage.” This is a project-specific phase distinction, not a general definition of machine learning or human biology.

**Evolution and operation:** It supersedes the second round's “adding memory without restarting” and the question of whether training counts as restarting. Earlier learning-layer and learning-forest terms still denote organization, abstraction and revision responsibilities; the phase vocabulary does not delete those mechanisms. T12 gradient updates should be called training. Recomputing `sim` representations is not automatically simple FSM memory writing. A T13 proposal does not establish implemented learning. Minimal FSM actions, startup boundaries and their complete interfaces to training remain open. Sources: R26:35–57; D54:527–609,840–863.

### E15 Flattening (project sense) — 抹平

The author's term concerns representing information without distinguishing the knowledge itself. It is not synonymous with using vectors or losing accuracy on old questions. R26's second correction withdraws an accusation based merely on the T series using vectors. T12 does not directly measure flattening. Neither score decreases nor vector proximity establishes its presence or absence. Tests for preservation of identities, information and paths remain to be defined. Sources: R26:7–26,59–69.

### E16 Crystallization / lattice / thermodynamics and entropy loss — 结晶／晶格／热力学与熵损失

Crystallization describes the design direction of knowledge progressively gathering from experiential relations. “Lattice” also names different concrete representations and constraints across experiments; see the implementation crosswalk. The author connects losses during chain changes to thermodynamics, referring to the event chain itself. This preserves a theoretical motivation without establishing physical entropy, a probability space, state equations or conservation laws. Training loss, energy use and entropy cannot simply be equated.

R26 clarifies that crystallization is intended to derive knowledge from experience, not create it from nothing. It does not measure preservation of all knowledge information in existing code. The thermodynamic correspondence and flattening tests remain open. Sources: R26:20–26; U-ENTROPY; E26.

### E17 “Based on our construction” and scope labels — “基于我们的构造”与 EA／CA／PA 边界

R26 permits calling the relevant small models “based on our construction,” restricted to EA / sentence-level scope, not the complete architecture. This scope description does not prove one sentence equals one node or chain. CA appears in that discussion, but an explicit complete meaning, English expansion or equivalence with PA was not established in the inspected material. Keep it unresolved. Sources: R26:15–16; U-KA.

### E18 Path interference / loss of knowledge — 路径受影响／知识丢失

Lower old-task scores are observations. Temporary inaccessibility, a readout mismatched to new coordinates, overwritten information and rapid subsequent relearning are different explanations. Drops after coordinate changes or recovery after old-task training do not alone exclude these alternatives. Compatibility with a concept is not positive experimental confirmation. New terminology must not rewrite frozen predictions or original scores. Sources: E26; R26; D54:768–805.

## How this compilation handles corrections

| Issue | Earlier interpretation / ambiguity | Current handling | Still open |
|---|---|---|---|
| Event chain | Chronological log or fixed language tree | Generalized AST / knowledge composition, with separate occurrence records | General execution semantics and learned encoding |
| Node | “The T series has no nodes” | Withdraw blanket claim; comparison-and-selection can be a what→what process | Other transformations and unified representation |
| First member / package | No explicit first member means it cannot be a package | Separate conceptual reference from explicit implementation; allow qualified usage | Indexed package objects and fixed references |
| Flattening | Infer it from vectors or lower scores | Neither is a sufficient criterion; round-two correction takes precedence | Testable information-preservation criteria |
| Learning | No restart / continued training means learning | Round three restricts the sense to post-startup FSM memory writing; training separate | Startup boundary and older learning-layer responsibilities |
| Hongchenxian chain | Transfer The Abyss's AST acceptance directly | Explain agent work chains and implemented engineering separately | Complete branching collaboration, original-identity recovery and long runs |

R26's ending still includes “no nodes / first member,” “possibly flattened” and “learning needs clarification,” contradicting the explicitly prioritized second and third rounds above it. This glossary follows that stated correction order, leaves the historical source unchanged and does not claim the discussion is finished.


<a id="core-terms"></a>

## Core concepts and mechanisms

C01–C41 cover the main categories of the existing glossary. Current R26 corrections take precedence over conflicting historical wording; responsibilities not revised remain in place.

### C01 Three question facets: what / why / how

Author's definition. What concerns knowledge and its organization, why concerns connection computation and generalized functional mappings, and how concerns practice, tools and process organization. An object can participate in transformations between facets; these are not permanently isolated modules. Each transformation needs explicit inputs, operations, outputs and feedback. The classification is not a proven completeness theorem for all computation. [D54:165–184,96–100]

### C02 Knowledge, memory knowledge and abstract knowledge

Author's definition, following the v0.53 classification. Knowledge includes memory knowledge and abstract knowledge; memory knowledge includes long-term and cached memory knowledge. Abstract knowledge concerns reusable combinations and relations. Long retention does not itself produce abstraction, and registration does not establish verification. These categories describe content roles, not disk versus RAM or persistent versus volatile storage. [D54:84–90,175–180]

### C03 Experience

Author's definition. Experience comprises occurrences and material arising from practice, observation, dialogue or corpora. D54 describes formation through decomposition and learning, rather than treating an unchanged input as already formed knowledge. Preserve provenance, conditions and the kind of material: receiving a claim, deriving a candidate and executing an action with feedback are distinct. Retaining source text does not establish its truth. [D54:175,184,713,740–750]

### C04 Memory and the memory layer

Author's definition. Memory organizes concrete experiences, relations, conditions, composition and time/version information; it is more than a final answer. The memory layer has a distinct functional role without requiring a separate physical database. External consumers may reference memory, but later mutable interpretations must not rewrite its original meaning. Immutability does not imply that forgetting is prohibited; retention scope still requires definition. [D54:174–176,717–734]

### C05 Long-term memory, cached memory and chained caches

Author's definition with engineering candidates. Unfinished subchains, progress, intermediate products and blocked attempts may belong to cached memory knowledge; a cache is not the opposite of memory. Transitions to long-term retention, retention periods and eviction remain undecided. Separating shared structures from instance state and saving consistent state before releasing active resources are candidate mechanisms. A record does not establish completion, unlimited retention or lossless recovery. [D54:24–81,84–90,126–134]

### C06 Concrete-knowledge repository, abstract-knowledge repository and intermediate binding region

Author's definition. The concrete-knowledge/memory side provides objects, experiences and applicability conditions; the abstract-knowledge repository holds reusable relations and combinations. Their intermediate binding region preserves correspondences between concrete objects and positions in abstract relations. Existing bindings may be reused, but a context-specific result does not become a universal answer. These roles do not prescribe a database count; read/write, invalidation and recovery interfaces remain open. [D54:198–199,213–231,247–267]

### C07 Learning layer and learning-material repository

Author's definition. The learning layer processes experience, locates changes and organizes revisions, supplying material for why-side mapping training. Material preparation is not completed parameter training. The learning-material repository renames one former why-side “memory repository,” not all memory. D54 routes concrete-content revisions through the learning layer into successor versions while preserving old versions; it does not require that layer to be the optimizer or sole authority over every product. [D54:181–184,513–521,545–549]

### C08 Material, original dictionary / soil and root knowledge

Author's definition. Material may be an original fragment, an existing package, or an objectified method or rule. The original dictionary/soil supplies initial material and stable identities; it is not an omniscient dictionary. A root is a referenceable starting point relative to the current layer, so an existing package can be a higher layer's root. Lower-layer products must actually enter higher-layer computation; repeatedly re-encoding the original corpus does not establish hierarchical combination. [D54:200,204–206,318–320,559–562; D57:19]

### C09 Objects, identity, registration and new concepts

Author's definition. Objects may include methods, relations and rules as well as things. Registration establishes a stable referenceable identity for an object or new combination. Equal names do not imply equal identities, and a package remains distinct from a reference member whose name it reuses. IDs provide addressing, not an inherent semantic ordering. Registration, learning, verification and publication are separate actions; identity formats and lifecycle rules remain engineering work. [D54:200–210,682; D57:13]

### C10 Knowledge package / index package, members and participation bindings

Author's definition. Knowledge package and index package name the same object. A package carries member organization, addressing, references, unfolding and computational grounds after commonality formation. Members retain identity, participation position, context, values and differences; one item may participate in several packages. Using a package need not unfold every descendant. Shared material does not imply shared participation bindings or answers. Package size, tensor layout and automatic formation criteria require implementation and validation. [D54:201,289–303,310,321,680–684]

### C11 Fixed reference and zero self-deviation

Current usage first separates concept from implementation: R26's second correction emphasizes a conceptual first member and does not make explicit anchor selection a prerequisite for using the term knowledge package. D54's historical implementation direction uses the first inserted member as a fixed reference rather than reselecting it for each query. This does not claim every experimental implementation already provides that interface. Package and reference-member identities remain distinct. Zero denotes self-deviation, not unknown, missing information or a shared identity for all roots. The reference need not be an average or typical example. Changing the semantic reference requires a successor structure; equivalent encoding migration is not automatically a semantic change. See E03, E17 and the correction table for the evolution. [R26:14,20,26–33] [D54:207–208,323–325,679; D57:15]

### C12 Finding commonality and preserving differences

Author's definition. Finding commonality groups similar material under the current comparison basis without claiming a unique classification. Preserving differences retains reference-relative distinctions inside a package so that they participate in locating, selecting and transforming members. Differences must accompany member references into subsequent computation, rather than surviving only in a side log. Similarity, package membership and shared structure do not establish semantic equivalence or truth. Encodings and transformation operators remain to be specified. [D54:309–316,323–325; D57:21]

### C13 Cost, loss, project-specific “bill” and relational evaluation

Project-specific terminology. Version 0.46 treats cost, loss and the project-specific “bill” as names for one concept, distinct from Hongchenxian resource settlement; deviation, match and confidence express relational evaluation at different interfaces. Each interface must still state the compared objects, reference, conditions, direction and scale. Bare values from different references cannot simply be added. Loss = 1 − match requires a declared scale, and “confidence” does not imply calibrated probability. This convention neither redefines standard machine-learning terminology universally nor establishes an entropy measurement. [D54:311–315,323,637–670]

### C14 Connections, paths, functions and domains / codomains

Author's definition. A connection is a generalized functional mapping rule; logic is expressed through conditionally reachable paths. A path needs inputs, a transformation and outputs, which may include several distinguishable candidates. Composition requires compatible interfaces or explicit conversion; a drawn arrow does not establish reachability. Both directions require their own conditions and retained information. This does not make arbitrary functions reversible, nor does producing candidates establish goal completion. [D54:209–211,221–227,273–277,437]

### C15 Reference-frame transformations and extended reference scope

Author's definition with a working interpretation. Extended reference scope concerns implicit reference changes between package, chain and outer-scope computations, not relocation of the original package's anchor. Specify source and target references, applicability conditions, preserved correspondences and gaps. Equal dimensionality does not guarantee compatible coordinate meanings. No universal lossless or reversible transformation has been established, and subtracting scores under different scales does not measure information loss. [D54:273–287,408,666–668]

### C16 Learning forest and working forest

Author's definition. The learning forest progressively combines material into knowledge and mappings; the working forest uses and unfolds existing combinations and accommodates new experience locally. These are formation/use roles, not two fixed neural layers. Lower-level combinations must become higher-level material while historical trees and provenance remain available. New experience must not directly overwrite global learning structures. Shared DAGs, persistence and parameter layouts are engineering choices. [D54:327–335,710–713; D57:19]

### C17 Stepwise learning, hierarchy and two training loops

Working agreement. Stepwise learning combines simple structures progressively; iteration within a layer does not automatically advance to another layer. The package loop forms and reuses local combinations; the EA loop uses existing packages as current roots and learns local relations with slots. Each loop may itself contain several levels. These loops do not replace the two forests or eliminate local generalization. Labels organize candidates but do not establish correct supervision; interfaces, losses and sharing remain open. [D54:317–320,553–566]

### C18 i / perspective transformation, seeds and growth criteria

Author-adopted placeholder concept. i denotes changes in organizing or comparison criteria and corresponds to the seed, while the original dictionary corresponds to soil. Different trees can grow from shared soil; choosing tree B does not overwrite tree A. Parameters, operators and selection mechanisms remain undefined. i is not merely a label change or scalar adjustment and is not assumed to obey complex-number or quaternion algebra. Time, versions and i are not interchangeable. [D54:204–205,335–341]

### C19 Partial decoupling, local scope and global scope

Author's definition. Components maintain relatively independent use/update boundaries while exchanging necessary content. Local working records differ from learned versions usable at broader scope; local success does not automatically become a global rule. Folding changes current participation, not all physical connections. Runtime scope, training write scope and behavioral impact scope must be stated separately: shared parameters can give locally supplied material a wider impact. [D54:300–303,333–334,543–549,807–812]

### C20 Slots: positions, constraints, candidates and bindings

Author's definition with editorial qualifiers. A slot is a relational structural position with scope and context, not an empty cell, vector row or transformation algorithm. Position, constraint, candidate material and binding are explanatory qualifiers, not four established modules. Version 0.41 retains linguistic roles as a bootstrap and extends toward general process positions; tokenization does not replace role identification. D54 preserves an established package's slot affiliation while particular occurrence bindings may change. [D54:365–391,48–58; D57:27]

### C21 KA, EA and PA: relational scope across abstraction levels

Later author clarification. KA handles member differences relative to a fixed reference within a knowledge package. EA refers to KA and SLOT when organizing relations and combinations among slots within a chain/sentence. PA handles relations between event chains; its classification is incomplete. These iterate the same reference-frame idea across abstraction levels, rather than constituting three independent theories. Words, sentences, paragraphs and documents are scale examples, not fixed layers. No attention formula or model count follows. Retain PA and describe it as inter-chain relational scope; do not invent its expansion or equate it with CA without confirmation. [U-KA; D54:399–408,429]

### C22 Attention, Q / K / V and knowledge vectors

Author's division of responsibilities with engineering interpretations. Attention computes associations within structures, contexts and candidate scopes; it does not alone perform registration, fact verification or execution. Q represents the current matching need, K candidate matching information, and V content used in computation. None replaces stable object identity. Knowledge vectors support matching and calculation rather than replacing complete memory and provenance. High weights do not establish truth, causality or calibrated probabilities; sharing and cross-level encodings require implementation. [D54:393–429,854–863]

### C23 FFN and the candidate matrix

Candidate modification. An FFN may participate in candidate representation, combination and difference computation; the name does not establish package formation. A candidate row must provide access to package/member identity, fixed-reference differences and the current evaluation. Missing evaluation remains unknown rather than being filled with zero. This semantic contract does not require one dense matrix and does not conflate a standard FFN with the final vocabulary projection. Layout and output interfaces remain open. [D54:186–191,633–644]

### C24 Anti-unification (AU) and REVIEW

Candidate mechanism, marked NOT_RUN in D54. Within bounded material and reference scopes, AU seeks shared structures while retaining each input's substitutions, bindings and provenance. It may assist initial combination, structural checks or REVIEW. A generalization does not establish semantic, factual or causal correctness. Triggering REVIEW does not authorize overwriting knowledge or moving a reference. The AU variant, acceptance criteria, budget and stopping rules remain undecided; finite inputs need not be cheap. [D54:611–631,734]

### C25 Main chains, subchains, protocols and the how outlet

Author's definition and working agreement. Main/subchain roles are relative to task scope. A subchain organizes and concludes work in its own scope, then returns a result or state. Protocols specify inputs, result interpretation and errors while preserving request/feedback correspondence. A chain's how outlet need not be exclusive to its parent, but this grants no external sharing permission. Main and subchains are related without sharing loss; physical resource costs remain. Fields, concurrency and recovery protocols are open. See the separate event-chain section for structure. [D54:118–124,441–475; D57:35–41]

### C26 Compensation through simulated subchain outcomes

Author's definition, narrowed in v0.26. Compensation means simulating a subchain's outcome; tool outcomes are one case, and actual execution is not compensation. The recorded scenario first acknowledges a missing capability or knowledge when a required tool is unavailable, then attempts simulation to continue reasoning. Simulation may fail and does not establish real capability or occurrence. A shared interface for simulated and actual calls is only a candidate; rehearsal provenance and limits on actual-side use remain necessary. [D54:233–239,483,809]

### C27 Local learning, local repair and counterexample localization

Working agreement. Exclude correspondences that can be reused directly, locate actual changes, and route material into the package or EA loop. Distinguish provenance, binding/context, within-package evaluation and reference-semantic problems; new facts need not automatically trigger retraining. Local material does not establish parameter isolation, so actual sharing dependencies determine impact checks. Node revisions create successor versions. Difference criteria, writable parameters, update interfaces and impact tests remain open; an effective local repair is not necessarily the least-cost repair. [D54:535–551,591–609,686–711; D57:47]

### C28 Mutual supervision across scales

Working agreement. Later-learned relations may revise earlier products, while local evidence may constrain outer scopes; this can recur at larger scales. “Fractal” is an organizational analogy, not a dimensionality proof. Outer scopes are not inherently correct judges, and same-source interpretations do not add independent evidence. Revisions preserve provenance, fixed references and versions. Whether feedback travels through material, structural constraints or gradients, and how shared parameters are affected, remains open. [D54:568–589]

### C29 Successor-version revision, versions and time

Author's definition. The project's “gray update” is best rendered here as successor-version revision: create a linked successor while preserving the original, rather than overwriting or saving an unrelated copy. A new occurrence differs from a revision of an old memory; old chains retain their historical version references. Version matching does not make only the latest version valid, and recency priority does not establish truth. Time, version numbers and improved quality are distinct; hashing does not replace a valid revision process. [D54:338–339,545–549,717–732]

### C30 Reverse formation, imagination and provenance

Author's definition. Knowledge can produce experience through practice, memory can prompt a current experience, and combinations of knowledge can form imagined memories. Tracing existing grounds, unfolding retained composition and forming new experience/memory are different operations. An act of imagining or replaying may occur, without making the imagined scene an external fact. Triggers, feedback and write mechanisms require implementation; simulated memory cannot simply be relabeled as actual experience. [D54:736–750,807–809]

### C31 Folding, unfolding and shared reuse

Author's definition. Unfolding brings required subprocesses into the current scope; folding removes their internals from active scope while retaining necessary results, interfaces, indexes and parent/child relations. “Excision” here does not delete memory, and “merging” does not conflate call identities. Preparation may be shared under compatible versions and dependencies, but current context-dependent computation remains. Unfolding cannot recover discarded information; re-execution is a new experience. Invalidation mechanisms still require implementation. [D54:289–303,595–597,752–766]

### C32 Memory boundary valve, world / premises and provenance boundaries

Author's definition with working interpretations. The boundary valve limits the current world, premises, domain and experiential working set; it is not another definition of self. Combination boundaries depend on each iteration's material, references and relations, not a once-for-all sentence split. Provenance boundaries distinguish occurrences and receptions. Unknown or unexpanded content must not be treated as illegal or nonexistent. Cache capacity, exit and invalidation policies remain to be specified. [D54:519–521,702–713,895–897; D57:27–31]

### C33 Backtracking, loops, package-based organization and reduction

Working agreement. Backtracking supports tracing, rerouting, diagnosis and material collection; it cannot undo actions that changed the world. A loop may reuse one subchain for several rounds rather than creating a new chain each round. Package-based organization handles local relations before higher-level reduction. Logarithmic depth under balanced grouping does not establish logarithmic total time or storage. Grouping rules, package sizes, scheduling and termination interfaces remain open. [D54:102–162]

### C34 Bounded-breadth expansion, resource pools and termination

Author's requirement with a working interpretation. Bounded-breadth expansion limits the current scope while preserving unresolved distinctions. Least action is a theoretical inspiration here, without a derived concrete algorithm. Rounds of the same loop share a finite resource pool rather than resetting it automatically. Reaching a budget means the current computation stops, not that the task is complete; incomplete state must be retained. Breadth, replenishment, stopping/resumption and candidate retention rules remain open; no top-k or threshold is supplied. [D54:112–116,156–162,831–850]

### C35 Divide-and-conquer streaming, CPU / GPU and stopping exploration

Later clarification available only through the published D57 digest. Version 0.55 makes divide-and-conquer streaming from startup, cycling work through local/CPU and GPU execution with small neural units, a core training requirement in the design rather than merely mini-batching a large network. “Startup” retains that older digest's usage; its complete correspondence to R26's initialization / post-startup learning phases remains unresolved. It does not prescribe one network per package or unloading weights every step. Versions 0.56–0.57 allow stopping when a solution is sufficient under finite conditions. In D54, symbolic/connection roles differ from CPU/GPU locations; resource benefits require measurement. [D57:43–55; D54:815–827; R26:48–57]

### C36 Underlying revisable FSM

Author's theoretical proposal. The FSM triggers activity and state transitions and may revise its mapping on grounded experience; the term does not require an immutable table. A state transition alone does not establish a memory write; R26's learning denotes post-startup FSM recording. It is tied to actual resources; continuous resource/state quantities with discrete triggers are an engineering interpretation. States, triggers, revision scope and version interfaces remain open. A local fixed-FSM experiment does not establish the complete revisable mechanism, life or autonomy. [D54:840–863,936–944; R26:48–57]

### C37 Self: definition / feeling / behavior

Author's working definition. Definition concerns the system's identity and history; feeling concerns current wants, thoughts, concerns and orientation toward action; behavior concerns what it can actually do and under which conditions. These are connected facets, not three selves or names interchangeable with modules. Direct access is understood through constituent relationships, not as making everything readable part of the self. This records the definition without establishing necessary/sufficient conditions for subjecthood or evidence of experience in this project. [D54:865–899]

### C38 Self scope, integration and project-defined incomplete self-integration

Project-specific convention. Whether a component belongs within self scope differs from how fully it is integrated or controlled in the current state. The author uses 自我缺失 for limits in integration or autonomous control. The editorial English suggestion is incomplete self-integration, explicitly qualified as project terminology rather than a medical term. Scales, thresholds and observables are undecided. Local autonomy does not automatically exclude membership, and the concept must not rank people or personhood. [D54:901–916,928–944]

### C39 Temporal/structural traceability, joint restoration and deterministic replay

Author's principle with engineering distinctions. Optimization must preserve identities, versions, provenance, bindings and dependencies sufficient to identify the grounds used at the time; “spatial” initially means structural positions and relational scope. Traceable explanation, restoration of compatible joint state and replay under a declared consistency criterion are separate capabilities requiring separate evidence. Logs alone guarantee neither restoration nor bitwise replay. Missing historical evidence cannot be reconstructed by assertion from current state. Changes to dependencies that affect a result should mark the relevant old result for review or invalidation; invalidation, checkpoint and retention policies remain engineering work. [D54:768–805]

### C40 Acceptance states and evidence levels

D54's evidence conventions. Analogy/inspiration suggests a direction; hypotheses/candidates await testing; working definitions/agreements record adopted concepts; special-case results cover stated constraints; empirical validation is bounded by data and conditions; mathematical guarantees require premises and proof. Implemented, executed and passed respectively require code, execution records and acceptance evidence. Unknown/not found does not mean nonexistent. NOT_RUN and REVIEW must not be rewritten as success, and terminology registration does not upgrade design evidence. [D54:9–16,946–957]

### C41 Traditional / function-centered approach and representation qualifiers

Project-specific names. In D54, “traditional” and “function-centered” both refer to the traditional Transformer under discussion, not two established schools. D54 does not supply complete standalone algorithms for “lattice point” or “hard boundary.” Object-vector rows, member slots, scalar score slots and semantic slots must be qualified by implementation. A missing grammatical edge does not automatically justify hard-masking an unknown relation. Later lattice, potential and entropy concepts and their experimental mappings belong in version-specific sections, not retroactively in D54 as defined or measured results. [D54:186–191,367–391,410–415; D57:31]


<a id="implementation-terms"></a>

## Implementation, protocol and experimental terms

This section describes specific uses in the repository's public code and archived experiments. An interface does not establish a completed algorithm. Concepts, code operations and validation are three evidence levels: designs state concepts, source defines current contracts, and run records describe what a particular version actually did under specified conditions. Old comments may describe earlier states. For example, `learning_store.py` now exists despite an older statement elsewhere; its registration interfaces still do not establish an automatic learning algorithm. The [design boundary][A11] and [implementation evidence][A12] delimit these levels.

### Hongchenxian: work coordination and source verification

| ID and term | Definition | Current code operation | Does not establish / must not be conflated with |
|---|---|---|---|
| **I01 Work event chain; execution trace** | Organization of agent tasks, collaboration, progression and feedback, with traceable records of calls, sources, dependencies and states. | In the current public slice, claims, bindings, admission, spend, tool results, final sources, receipts and settlements reference one another. [Architecture][H1] | Does not automatically implement The Abyss's knowledge-process AST or every work-branching mechanism; recording a learning discussion or a successful call does not establish learned knowledge. |
| **I02 Body; lifecycle controller** | A member's lifecycle and source-ledger controller; Body remains a proper component name. | Persists states, tickets, bindings, sources and processing records; qualified sources drive state changes. [Body][H2] | Not a physical body, personality, consciousness or neural memory model. |
| **I03 Member identity; session identity; policy epoch/digest** | Protocol identifiers fixing a participant, session and policy version. | Binds and checks `actorId`, `sessionId`, `policyEpoch` and `policyDigest`. [Lifecycle adapter][H8] | Identifier/hash consistency is not cryptographic authentication or host-level writer exclusion. |
| **I04 Private memory; paragraph memory** | Original text, paragraphs and references scoped to a member. | Body records synchronize into paragraph storage with indexing, pagination and original-text windows. [Memory references][H3], [paragraph storage][H4] | Private denotes protocol scope, not guaranteed encryption. These records are not The Abyss's learned memory or abstract knowledge. |
| **I05 Index; preview; original-text retrieval** | Distinct stages from locating a reference to retrieving selected source text. | Search an index, inspect a preview, then read selected originals under query, cursor and budget contracts. [Recall adapter][H5] | An index or summary is not the original text. Window and budget limits do not authorize deletion or automatic forgetting. |
| **I06 Fixed round snapshot; pinned reference; short round reference** | A fixed round and memory view. | Snapshots bind a roster, shared epoch, references and topic; short references carry round identities and digests; pins do not silently drift to the latest state. [Router][H6], [short references][H7] | Not a global knowledge version or permission to disclose private text. Digests do not replace original content. |
| **I07 Claim; dispatch ticket; request binding; queue acknowledgement** | Claiming work, its ticket, its bound request and its queued acknowledgement are distinct objects. | Claim a ticket for a ready source and bind identity, input and provenance; ack records queuing. [Body][H2], [memory references][H3] | A ticket is not completion evidence; ack is not a model result or task success. |
| **I08 Step admission; prepared record** | Permission for this step to enter transport and its preparation record. | Checks the active ticket, policy, request header and input before recording admission/preparation. [Lifecycle adapter][H8], [step transport][H10] | Admission/preparation is not a call, response or completed settlement. |
| **I09 Protected transport; spent record; terminal record** | The actual request boundary and records of a consumed attempt and its termination. | Checks serialized requests; records spent before the injected forward; records response/termination separately. [Protected wire][H9], [step transport][H10] | Spent is not success or verified real billing. The protection layer is not a general malicious-code sandbox. |
| **I10 Native tool call; observed tool result** | A call and a source-anchored result in the integrated event protocol. | Matches call IDs, steps, assistant source events and corresponding results. [Source completion][H11] | Native does not mean this preview executed the real official SDK. Tool output is not automatically a final opinion or lifecycle decision. |
| **I11 Completed source; Body acceptance** | A complete qualified ending source and the Body's acceptance of it. | Checks turn, step, tool-result and final-text evidence; Body stores the final source and parsed decision. [Source verification][H11], [Body][H2] | Protocol completion does not establish factual truth or external task success, nor that all subsequent local records already exist. |
| **I12 Lifecycle receipt** | A local record referencing the same ticket, completed source and proof digests. | Stores ticket/source identity, ending event and digests and reconciles them with the source. [Recovery verification][H12] | Not an arbitrary tool return or payment receipt. Distinguish it from an experimental result receipt. |
| **I13 Step settlement; ticket settlement** | Reconciliation of consumed requests with termination, result sources and final receipt. | Verifies each spent step and its evidence; ticket settlement requires consistent step records and final receipt. [Step transport][H10] | Not proof of truthful model statements, accurate real costs or reversal of external side effects. |
| **I14 Opinion staging; round release** | An explicit opinion from a qualified final source enters a fixed round, followed by a round observation. | Stages opinions after snapshot checks; release includes opinions and absences and sets `executionAuthorized:false`. [Short references][H7], [router][H6] | Staging is not consensus. Release is not action authorization or disclosure of every private thought. |
| **I15 Protected duty; recorder; historian; duty handoff** | Coordination responsibilities with explicit terms, succession and coverage conditions. | Checks qualified successors and their own source acknowledgements; records duties, rest and coverage gaps. [Duty protocol][H13], [router][H6] | Another actor cannot turn absence into consent. These are coordination duties, not learning modules. |
| **I16 Awake; sleeping; stopped; lifecycle decision** | Protocol states and the `continue/sleep/stop` decisions. | Parses a valid final-text envelope and advances Body state. [Decision envelope][H14], [Body][H2] | Not evidence of consciousness, sleep learning or forgetting. Tool output, errors and resource holds are not member decisions. |
| **I17 Held state; reopen; evidence reconciliation** | Preserving uncertainty, reopening storage and filling missing local records from completed-source evidence. | Unknown, conflicting, foreign or incomplete sources remain held; only complete consistent evidence permits recovery of the same ticket. [Architecture][H1], [recovery][H12] | No resend on exception, no tool re-execution and no rewriting a later decision as earlier success. Not sleep/wake or generic power-loss recovery. |
| **I18 Append-only records; source lineage; hash** | Retained originals and checkable references/byte identities. | Checks source digests, identities and relationships among records. [Architecture][H1] | Hashes do not establish truth, authorship, exclusive writing authority or production durability. |
| **I19 Test double; fixture; synthetic data** | Controlled interface substitutes, fixed test setups and constructed data. | Public tests use local SDK/provider doubles and synthetic identities; the official loader refuses execution. [Scope][H16], [evidence levels][H15] | Ten identities are not ten-member concurrency. Real SQLite plus simulated reopen is not proof of real-server, cross-process or power-loss recovery. |

### The Abyss core: structures, occurrences and recording interfaces

| ID and term | Definition | Current code operation | Does not establish / must not be conflated with |
|---|---|---|---|
| **I20 Generalized AST; process structure; path** | Reusable combinations of objects, relations, conditions and processes; paths involve selection and transformation among them. | `ProcessStructures` stores versioned nodes, kinds, constrained slots, child nodes and slot mappings; `unfold` reads retained composition recursively. [event_ast][A1] | More than a work log. Reading structure does not establish semantic equivalence of folding/unfolding, automatic formation or a general executor. |
| **I21 Occurrence record; occurrence instance** | A concrete instance of a structure version and its evidentiary basis. | `Occurrences` links a structure version, parent occurrence, child position, cache and exactly one experience/memory basis, recording bindings. [event_ast][A1] | Existence of an occurrence does not prove external execution of a plan. Source type and verification evidence remain necessary. Instance and reusable structure are connected but distinct. |
| **I22 Facet-transition record; nine-cell transformation scheme** | Concrete inputs, outputs and transformation responsibilities among what/why/how. | `record_flow` records from/to facets, input/output references and a note on an occurrence. [event_ast][A1] | Not a fixed node label or nine-step pipeline. Recorded transitions do not establish implementation of all nine operators. |
| **I23 Role/argument slot; binding; candidates; gap** | A structural participation position and its current binding state. | `BOUND/CANDIDATES/GAP` distinguish a bound reference, multiple candidates and an unknown gap; parent/child mappings can enforce object identity. [event_ast][A1] | Unknowns are not zero or invented objects. Structural slots differ from experimental member slots and G1 score slots. |
| **I24 Experience record; source type; verification status** | Provenance of an occurrence or received item, with separate verification information. | `ExperienceLog` distinguishes statements, observations, tool descriptions/plans/executions, inferences, computations and recalls; verification is separately recorded. [experience][A2] | Receiving a statement is not verifying it; retaining an inference is not validation. Teaching feedback and factual verification also permit different source types. |
| **I25 Formed memory; recall; imagination; logical forgetting** | Memory content with formation evidence, scope and version lineage. | `MemoryLayer` records methods and experience/package-version sources; revisions append versions, recall adds an experience, and forget/restore changes reachability. [memory][A3] | A `form` interface does not complete a decomposition-learning algorithm. Recall does not make old content a present external fact. Unreachability is not deletion from disk/backups. |
| **I26 Learning-material repository; training provenance record** | References to sources for particular learning purposes and records of their use. | `LearningMaterialStore` stores memory/experience/call references; `record_training` links material to parameter versions. [learning_store][A4] | Inclusion is not verification; the recording interface does not train a model. Not all memory is training material. |
| **I27 Working cache; memory boundary valve; world; premise** | Current material visibility, applicable context and premise scope. | `MemoryValve` records worlds, entry/exit, priorities, candidate/active/revoked premises and calls requiring recheck. [valve][A5] | Activation/priority is not truth. Default physical does not verify content. Exit does not delete history; a recheck flag does not recompute results. |
| **I28 Knowledge/index package; member; fixed reference; version** | Two names for the same knowledge carrier, with membership, reference and revision identities. | `PackageRegistry` retains identities, values, differences, sources and computation contracts; the first member fixes the reference; changes append versions and distinguish local/global/publication status. [registry][A6] | Stable identity does not freeze every parameter. Material IDs are not ordered semantic quantities. Registration, publication and scientific validation differ. |
| **I29 Computation record; candidate row; local correction** | A package-level call and its inputs, candidates, selection, unknowns, feedback and revision evidence. | `CallLog` records calls; R1 corrects inputs/bindings, R2 package evaluation, and R3 reference/structure cropping; originals remain. [calls][A7], [corrections][A8] | Recording is not executing an algorithm. REJECTED means not selected this time, not false. RESOURCE_STOP does not establish exhaustive search or convergence. |

### Operational differences behind shared experimental terms

| ID and term | Operational use | Distinctions that must remain explicit | Public source |
|---|---|---|---|
| **I30 KA / EA / CA** — experiment-specific computation units | T1–T4 use these for local roles such as package computation, within-chain event selection and between-chain selection. In v18.1 CA processes historical member events and EA includes candidate-to-history cross-attention. | Attach the track/version; a local role is not a universal definition of attention. | [Implementation overview][A9], [checkpoint][R2] |
| **I31 Lattice representation; reference vector; grouping** | T5–T7 largely use supplied structures/vectors; T8 grows vectors through co-occurrence, PPMI and SVD; v18.1 additionally groups word vectors using thresholds. | Lattice is a representation term here, not proof of all mathematical lattice properties or natural semantic classes. Track-specific vector/group definitions are not interchangeable. | [T1–T10 summary][R1], [checkpoint][R2] |
| **I32 Package; member slot; alias; score slot** | T1–T11 source packages are synthetic generator families. v18.1 uses selected whole words and aliases may share member slots. G1 maps atoms to shared scalar slots. | AST role slots, word-member slots and parameter slots differ. Shared slots can lose identity; slot prediction does not demonstrate discrimination of every original word. | [Registry][A6], [checkpoint][R2], [G1][R5] |
| **I33 Experimental event sequence** | T5–T11 use fixed-length synthetic relation/object sequences; v18.1 extracts member events from clauses and takes a history window. | These local representations do not complete the generalized AST. Eight v18.1 history events are not eight complete clauses, nor Hongchenxian work logs. | [T1–T10 summary][R1], [checkpoint][R2] |
| **I34 Attention; pairwise block; comparator** | T11 pair averages pairwise products passed through an MLP. v18.1 retains Q/K/V and substitutes `tanh / L` for softmax. G1 uses logistic regression on shared scalar differences. | Pair does not name one common control. T11 parameter counts differ; do not claim matched capacity/FLOPs or use G1 as attention validation. | [Structured results][R3], [G1][R5] |
| **I35 Answer supervision; selection supervision; choice_two** | T5–T11 supervise the target object's binary answer. v18.1 directly supervises the correct slot. `choice_two` measures target selection only on exactly-two-candidate questions. | Equal candidate answer bits provide no identity-selection signal. Answer accuracy differs from selection accuracy. A 50% chance reference does not forbid scores below 50%. | [T1–T10 summary][R1], [checkpoint][R2] |
| **I36 IID; new-package transfer; old-stage result; continual learning** | T11 new-package vectors already use answer-free experience chains; test_new measures comparator transfer. T12 start.new precedes continual learning. | New-package testing is not completed new-package supervised/continual learning. Old-stage receipts do not establish subsequent learning, forgetting or retention. | [Checkpoint][R2], [fixed ongoing snapshot][R4] |
| **I37 Purity check; sibling win rate; unknown rejection** | v18.1 checks predefined impurity probes and origin-cosine thresholds; sibling win rate compares the true slot with the strongest same-package distractor. | Not semantic purity or conditional word-sense accuracy. All-illegal-candidate unknown probes primarily check the masking contract, not open-world unknown detection. | [Structured results and limitations][R3] |
| **I38 Grouping granularity; representation collision; post-hoc lookup reference** | G1 changes shared-score mapping on fixed atomic questions, credits same-slot ties by 0.5, and uses test-label group-pair majorities for diagnosis. | Effective degrees of freedom change; family priors are supplied. Lookup is not used for training/selection or an arbitrary-model bound. Prior propagation across disconnected graphs is not structure discovery. | [G1 results][R5], [G1 source][R6] |
| **I39 Receipt completion; scoped pass; static validation; independent reproduction** | A receipt records a completed experimental unit. Pass requires a named criterion. Static checks inspect syntax, structure or hashes. Reproduction requires a new execution and its evidence. | Counts such as 40/40 or 50/50 are not theory-success rates. Python AST parsing does not validate the empiricist AST's execution. Historical passes do not transfer to modified public copies. | [Implementation evidence][A12], [T1–T10 summary][R1] |
| **I40 Frozen-run manifest; preparation audit; historical verification** | Source/data identities and preparation records. G1's `training_started:false` is pre-training; its ten-seed audit records preparation, while execution stopped at 2/10 seeds and 28/140 cells. | Historical hashes do not publish omitted data/weights. Summaries cannot directly reconstruct the old run; fresh runs need new freezes/results. | [G1 results][R5] |

### I41 Experiment identifier and research stage

An identifier locates a particular generator, model, budget and evidence set; it is not a uniform capability level. This index does not rewrite original criteria or remove counterexamples.

| Label | Operational scope in current public material | Not implied by the label |
|---|---|---|
| T1 | Constructed combination tasks and layered spiral training. | General superiority over all baselines or Transformers. |
| T2 | Specified changes routed to KA_local, EA and CA revisions. | Autonomous diagnosis of arbitrary changes; update counts equal total cost. |
| T3 | Specified mutual-support structures and post-hoc stability analysis. | Failure of an untrained indirect package is an independent discovery; post-hoc simulation is online stopping validation. |
| T4 | Fixed-FSM operation, revision and injected-interruption recovery. | Synthetic ten days are ten real days; Hongchenxian, forgetting or autonomous coding is implemented. |
| T5 | Lattice/attention controls on fixed content-selection tasks. | Attention is necessary or every preregistered proposition passed. |
| T6 | Separating lattice parts and comparing alternative comparators. | A hand-written sim score establishes autonomous rule formation. |
| T7 | Fixed per-object perturbations of supplied vectors. | Robustness to every noise type or automatic compensation for ambiguity. |
| T8 | Growing reference vectors from synthetic-chain co-occurrence. | Complete difference retention or validated mixed old/new coordinate chains. |
| T9 | Growing visible query/relation tables and replacing them by windows. | Automatic world-change detection, full version retention or general causal learning. |
| T10 | Changing the initial scale of relation embeddings. | S2 or new-package transfer has been solved. |
| T11 | Changing distinct chain pools and relation embeddings at fixed update budget. | Only granularity changed; more distinct chains must help or hurt. |
| T12 | Staged old-task and subsequent-learning research; public status is a dated snapshot. | Old-stage completion is continual-learning completion, or a counterexample to one H1 refutes the whole theory. |
| v18.1 | Text-derived eight-candidate member-slot selection with joint filtering, grouping, alignment, sealing and replay changes. | Open-ended QA, an isolated granularity effect or guaranteed semantic purity. |
| G1 | Newly executed fixed-task shared-scalar pilot stopped by its resource gate. | Ten-seed success, stable optimal granularity, discovered family structure or neural-architecture validation. |

Sources are the [historical T1–T10 summary][R1], [T11/v18.1 checkpoint][R2], [fixed T12 snapshot][R4] and [executed G1 pilot][R5]. Learning, chain, package, recovery and completion have different operational roles in these contexts. Cite the track, version, task and validation scope together.

[H1]: ../projects/hongchenxian/docs/ARCHITECTURE.en.md
[H2]: ../projects/hongchenxian/research/central-step/vendor/hcx-fish-pool-20261106-v01/body.mjs
[H3]: ../projects/hongchenxian/research/central-step/vendor/hcx-native-lifecycle-adapter-20261106-v02/memory-reference.mjs
[H4]: ../projects/hongchenxian/research/central-step/vendor/hcx-round-recall-bridge-20261106-v01/vendor/paragraph/paragraph-memory.mjs
[H5]: ../projects/hongchenxian/research/central-step/vendor/hcx-round-recall-bridge-20261106-v01/vendor/recall-adapter.mjs
[H6]: ../projects/hongchenxian/research/central-step/vendor/hcx-continuity-round-router-20261106-v01/router.mjs
[H7]: ../projects/hongchenxian/research/central-step/vendor/hcx-assembly-shortref-20261106-v02/shortref.mjs
[H8]: ../projects/hongchenxian/research/central-step/vendor/hcx-native-lifecycle-adapter-20261106-v02/native-lifecycle.mjs
[H9]: ../projects/hongchenxian/research/central-step/protected-wire.mjs
[H10]: ../projects/hongchenxian/research/central-step/vendor/hcx-native-lifecycle-adapter-20261106-v02/step-transport.mjs
[H11]: ../projects/hongchenxian/research/central-step/vendor/hcx-native-lifecycle-adapter-20261106-v02/source-completion.mjs
[H12]: ../projects/hongchenxian/research/central-step/recovery-evidence.mjs
[H13]: ../projects/hongchenxian/research/central-step/vendor/hcx-protected-duty-20261106-v01/duty.mjs
[H14]: ../projects/hongchenxian/research/central-step/vendor/hcx-fish-pool-20261106-v01/pool-choice.mjs
[H15]: ../projects/hongchenxian/docs/EVIDENCE.en.md
[H16]: ../projects/hongchenxian/README.en.md
[A1]: ../projects/the-abyss/implementation/project/empirical_core/event_ast.py
[A2]: ../projects/the-abyss/implementation/project/empirical_core/experience.py
[A3]: ../projects/the-abyss/implementation/project/empirical_core/memory.py
[A4]: ../projects/the-abyss/implementation/project/empirical_core/learning_store.py
[A5]: ../projects/the-abyss/implementation/project/empirical_core/valve.py
[A6]: ../projects/the-abyss/implementation/project/empirical_core/registry.py
[A7]: ../projects/the-abyss/implementation/project/empirical_core/calls.py
[A8]: ../projects/the-abyss/implementation/project/empirical_core/corrections.py
[A9]: ../projects/the-abyss/implementation/README.en.md
[A11]: ../projects/the-abyss/DESIGN.en.md
[A12]: ../projects/the-abyss/EVIDENCE.en.md
[R1]: ../projects/the-abyss/implementation/historical/RESULTS.en.md
[R2]: ../projects/the-abyss/evidence/2026-11-07/README.en.md
[R3]: ../projects/the-abyss/evidence/2026-11-07/RESULTS.json
[R4]: ../projects/the-abyss/evidence/2026-11-07/ongoing_snapshot.json
[R5]: ../projects/the-abyss/research/g1-granularity-20261107/RESULTS.en.md
[R6]: ../projects/the-abyss/research/g1-granularity-20261107/pilot.py

<a id="sources"></a>

## Sources, evolution and open questions

Chinese and English entries share identifiers; translated labels do not introduce separate definitions. Limits and open questions are part of each entry. Where no new correction is listed, the cited usage is retained, not declared validated. **2026-11-07** follows the project's local date; source verification occurred at **2026-11-06 17:25 UTC**. Later changes should receive another version.

| Source ID | Inspected material and purpose | Access and limits |
|---|---|---|
| D54 | Empiricist AI Project Glossary, discussion v0.54, updated October 31, 2026, 09:56 UTC+08; original line references | Complete local reference copy and SHA256 checked; technical paraphrases only, without private quotations or the full original |
| D57 | Public [Abyss design digest](../projects/the-abyss/DESIGN.en.md) and [source notes](../projects/the-abyss/SOURCES.en.md), reporting selected updates through v0.57 | The complete v0.57 glossary was not obtained in this pass. No line-by-line audit of that original is claimed, and v0.54 is not called the globally latest version |
| R26 | User-confirmed Terminology Crosswalk, local project date November 7, 2026; three correction rounds; 69-line local file | Technical record and digest inspected. Author definitions and researcher experiment mappings have different authority. Full underlying chat was not obtained; superseded ending remains inconsistent |
| T13 | Slice Draft, November 7; observed revision includes a proposed FSM path-memory arm | Draft and digest inspected; only the draft observed in its directory. Earlier small-model scope and later LLM/tool directions coexist; still evolving |
| A0 | [Event-chain registry core](../projects/the-abyss/implementation/project/empirical_core/event_ast.py) and [core changes](../projects/the-abyss/implementation/docs/CORE_CHANGES.md) | Public code used to establish interface scope and gaps; static reading is not runtime validation |
| H0 | [Hongchenxian entry](../projects/hongchenxian/README.en.md), [architecture](../projects/hongchenxian/docs/ARCHITECTURE.en.md), [evidence](../projects/hongchenxian/docs/EVIDENCE.en.md) and central-step code | Offline synthetic/double scope, not proof of a full production or knowledge-learning system |
| E26 / V18 | [Dated research evidence](../projects/the-abyss/evidence/2026-11-07/README.en.md) and its source digests | v18.1 and T11 are reviewed historical records; T12 is an incomplete, time-bounded stage snapshot, without independent retraining |
| G1 | [Granularity pilot](../projects/the-abyss/research/g1-granularity-20261107/RESULTS.en.md) and [preregistration](../projects/the-abyss/research/g1-granularity-20261107/PREREG.md) | 2/10 complete seeds and 28/140 units before a resource gate stopped execution; the remaining seeds incomplete and excluded from the summary |
| U-AST / U-COMPOSE | Inspected author history: generalized AST on October 25; knowledge composition and event chains on October 31 | Technical definitions paraphrased; no chats, personal address terms or message identifiers published |
| U-KA | November 2 author clarification of KA / EA / PA scopes and iterative application of reference-frame ideas | Does not supply PA / CA formulas or establish their equivalence |
| U-HCX | November 5 author distinction: agent work event chains | Does not transfer The Abyss's theory or acceptance, or equate paragraphs with ledger events |
| U-ENTROPY / U-ITER | November 5 chain-change / entropy-loss motivation; November 6 loop, iteration and accumulation direction | Research usage and motivation, not thermodynamic proof, proven learning advantage or a global-optimum guarantee |

File versions, SHA256 digests, public entry points and access gaps are listed in [GLOSSARY_SOURCES.json](GLOSSARY_SOURCES.json). Digests identify inspected bytes; they do not authenticate every claim or make an unpublished original independently reproducible.

<a id="meeting-agenda"></a>

## Meeting discussion agenda

These are open questions, **not agreed conclusions**. Record whether each item retains the current definition, adds a qualifier, creates a successor version or remains undecided, together with its grounds. The meeting need not finalize every mechanism.

| ID | Question to align | Established basis and limits to retain | Useful meeting record |
|---|---|---|---|
| M01 | What are the minimal meanings of event chain, node and one path step? | Generalized AST / knowledge composition is explicit; comparison-and-selection can be what→what. Object-vector rows, structure nodes, paragraphs and ledger events are not automatically one-to-one. | A positive example and a misleading counterexample for structure, action and occurrence; list transformations without algorithms. |
| M02 | How do folding, unfolding, nesting, sharing and loops differ? | Structure and instance are linked but distinct; computational backtracking does not undo real actions or erase failed experience. | Identities, bindings, versions and outputs each operation must preserve; semantic-preservation properties still needing tests. |
| M03 | How does conceptual firstness map to a reference and implemented package? | R26 permits conceptual firstness; D54's first-inserted fixed reference is a historical implementation direction. Neighboring vectors do not automatically implement a package protocol. | Distinguish conceptual existence, explicit anchor, addressable package object and changing trained numeric values. |
| M04 | How do the new learning / initialization phases connect to older learning layers and streaming training? | R26 round three restricts this learning sense to post-startup FSM memory writing; older text also discusses learning forests, abstraction and training startup. | Names and interfaces for startup, FSM writes, vector recomputation, gradient training and structural revision; do not revive the withdrawn restart criterion. |
| M05 | How do KA / EA / PA relate to CA? | Current package-internal KA, chain-internal EA and inter-chain PA scopes are documented; CA occurs in experiments and discussion but its equivalence to PA is unconfirmed. | Define usage by track first, then decide whether to unify labels; no guessed acronym expansions or formulas. |
| M06 | How do the two memory-store senses, path memory and occurrence records connect? | Agent work memory and concrete–abstract mappings have different roles; T13 proposes a path-memory arm whose method is unsettled. | Minimal write/read objects, provenance, versions, unknown and failure states; preserve the distinction between T13 proposals and results. |
| M07 | How can flattening be distinguished from retained but unreachable knowledge? | Vectors, old-task drops, coordinate-change drops and retraining recovery do not individually establish their cause. | Observable information-retention criteria and controls for readout mismatch, rapid relearning and other explanations. |
| M08 | Are crystallization, entropy loss and loop-plus-iteration definitions, analogies or testable hypotheses? | The motivations are preserved; no unified physical quantities, equations or evidence of global advantage from local scores is established. | Separate meanings, measurable quantities, hypotheses and possible counterexamples; do not relabel analogy as law. |
| M09 | How should terminology and experiment interpretations evolve without erasing counterexamples? | The complete v0.57 original was not obtained; R26 retains superseded wording; frozen experiment contents must remain. | Source authority, replacement relationships and dates; compare the original when available and version later interpretations without rewriting frozen predictions or scores. |

Discovering and testing knowledge aggregation / splitting granularity also remains open. G1 varies supplied groups and hard sharing; it does not establish natural optimal granularity of real knowledge. Its resource stop and unfinished seeds remain part of the record.

### Revision rule

For new definitions, record the source date, replaced statement, scope and open issues. For experimental usage, specify fields read and written, labels, visible information and measurements. When theory-to-experiment mappings change, append an interpretation version while preserving frozen plans, failed predictions and original results. Clearer definitions reduce ambiguity; they do not turn compatible explanations into confirmed conclusions.
