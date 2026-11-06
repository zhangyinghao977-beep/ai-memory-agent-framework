# The Abyss and Hongchenxian / 深渊与红尘仙

English · [简体中文](README.md)

One repository, two separate research projects. **This is a bilingual research preview. The latest local Abyss source still awaits integration and review. The project license has not been selected; public availability does not grant an open-source license.**

## Two entry points

### [The Abyss / 深渊](projects/the-abyss/README.en.md)

1. **Logic is the reachable path through knowledge.**

This is a theoretical proposition of the project, not a conclusion established by experiments. The project examines how experience forms reusable knowledge, how knowledge is composed and unfolded, and how new experience leads to revision. Its entry point provides the design, sources, and evidence boundaries in Chinese and English.

The latest local source and synthetic-experiment inventories have been confirmed. An isolated candidate is still being prepared and reviewed. This directory currently provides theory documents; it does not establish that the complete source has been integrated, independently reproduced, or has passed every experiment. Complete experiment receipts and results meeting expectations are different states.

### [Hongchenxian / 红尘仙](projects/hongchenxian/README.en.md)

Research on collaboration among black-box agents: persistent identity, paragraph-indexed memory, frozen shared snapshots, per-step call accounting, lifecycle decisions, and source-verified recovery. This candidate includes an offline synthetic engineering path using only Node built-ins.

Hongchenxian's work-event chain covers work records, calls, dependencies, suspension, and continuation. It is not evidence that The Abyss's knowledge-composition learning, generalized AST, internal nine operators, or separate learning-event chain have been implemented.

## Running and interpreting evidence

These commands run only Hongchenxian's offline tests. They do not train an Abyss model:

```sh
node --version  # Verified runtime: Node.js 24.22.1
npm test
```

No npm install, Python, official model SDK, or API key is required. Tests create synthetic data in temporary directories. The default guard rejects common Node network entry points to prevent accidental calls; it is not a hostile-code sandbox. Do not supply real data paths or credentials.

Hongchenxian offline tests were rerun for this checkpoint: 72/72 passed. See `evidence/VALIDATION.json` for scope. This does not include reproduction of the latest Abyss source. The integrity manifest covers only this checkpoint; later source integration or file changes require renewed scanning, validation, and an updated manifest.

## Repository layout

- `projects/the-abyss/`: bilingual theory and evidence boundaries, with space reserved for reviewed current implementation.
- `projects/hongchenxian/`: source, synthetic tests, and bilingual documentation.
- `scripts/`: offline-call guard, candidate scan, and integrity verification.
- `evidence/`: source inventories and scope-qualified validation records.
- `docs/`: shared exclusions and release checklist.
- `third_party/`: a separate upstream license record; it does not select this project's license.

Theory, implementation, execution, acceptance results, and results below expectations are recorded separately. No claim is made of completed recovery of ten real members, 72-hour continuous operation, general learning ability, a complexity breakthrough, or consciousness.

## Before publication

Read the [exclusions](docs/EXCLUSIONS.en.md), [release checklist](docs/RELEASE_CHECKLIST.en.md), and [third-party notices](THIRD_PARTY_NOTICES.en.md). Do not upload the original working directory wholesale. Real sessions, private conversations, accounts, credentials, original training data, and unreviewed operational records are excluded.
