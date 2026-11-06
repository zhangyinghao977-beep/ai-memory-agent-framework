# Hongchenxian / 红尘仙

[简体中文](README.md) · [Repository entry](../../README.en.md)

**Glossary:** [Complete bilingual glossary](../../docs/GLOSSARY.en.md) distinguishes agent work event chains, empiricist AST structures and occurrence records.

This directory studies collaboration among black-box agents. It contains an offline engineering path for native memory-tool calls, a final lifecycle decision, per-step usage accounting, source verification, and conservative recovery after interruption. It does not implement The Abyss's complete empiricist learning architecture.

This is a research candidate, not a deployable product. It contains no real member data, model credentials, or server entry point.

## Quick start

Run from the repository root:

```sh
node --version
npm test
```

Verified environment: Linux and **Node.js 24.22.1**. Only Node built-ins are used, including `node:sqlite`. No npm dependency installation, Python, official SDK, or API key is required. Other runtimes and operating systems have not been verified.

Default tests load an accidental-network-call guard before using local synthetic fixtures. They create synthetic SQLite data and session files in temporary directories. This guard is not a hostile-code sandbox. Do not supply real data paths or credentials to these modules.

## Implementation scope

- Body, private member memory, indexes, previews, and selected original-text retrieval.
- Frozen round snapshots, protected recording duties, and short-reference opinion acceptance.
- Multiple tool steps followed by one final lifecycle decision, with per-step request and settlement records.
- Source-verified recovery for the same ticket; unknown or conflicting outcomes remain held rather than being blindly resent.
- SDK/provider doubles with normal, reopen, interruption, and fault-injection cases.

The session-persistence double simulates flush/reopen using in-memory structures. SQLite databases are real local databases, but these tests do not prove power-loss durability, production permission isolation, or cryptographic identity authentication. Ten synthetic identities do not prove ten-member concurrency; staging one opinion does not prove a complete assembly.

## Version and evidence

The code consists of 32 modules from sealed central-step v04. Thirty are unchanged; two preview changes remove the official SDK loader and replace one deployment static check with a no-SDK-load test. In v02, source files are only relocated into this project area. The repository-root `evidence/SOURCE_MANIFEST.json` records provenance and byte changes.

The [evidence document](docs/EVIDENCE.en.md) distinguishes local doubles, official synthetic runs, and real experiments. Complete recovery of the original identities and at least 72 hours of continuous operation have not been demonstrated. Similar theory, complete logs, and model self-description are not substitutes for acceptance evidence.

## Reading

- [Architecture and boundaries](docs/ARCHITECTURE.en.md)
- [Dependencies and reproduction environment](docs/DEPENDENCIES.en.md)
- [Experiments and unexecuted scope](docs/EVIDENCE.en.md)
- [The Abyss theory entry](../the-abyss/README.en.md)

The owner must decide the project license and contribution attribution. The upstream MIT text at the repository root preserves a third-party notice; it does not select MIT for this project.
