# Sources and editorial notes

[中文](SOURCES.md) | [English](SOURCES.en.md)

## Project materials

This directory was compiled from the accessible materials below. The original materials are not included as public originals in this directory. Titles and versions identify provenance without providing private storage links or requiring readers to access private accounts.

1. *Empiricist Transformer: Core Design Draft*, 2026-10-22. Used for the central knowledge carrier, two forests, tokenization bootstrap, substitution revision, cross-layer inputs, candidate attention/FFN designs, leakage boundaries, and validation suggestions. The original explicitly presents a design and reports no new experiments.
2. *Empiricist AI Project Glossary*, discussion version v0.57, updated 2026-11-02 at 11:09 (UTC+08). The source filename retains 20261023, which is not its version date. Used for knowledge classification, fixed references, learning-layer revision, main chains and subchains, caching, packaging, divide-and-conquer streaming, and exploration boundaries. The distinctions among current definitions, working interpretations, candidates, and unresolved items are retained. Private quotations and full historical conversations are excluded.
3. *2026-10-10 Empiricist Artificial Intelligence Overall Architecture Snapshot v0.1*. Used only for historical engineering evidence boundaries. Its local implementations, synthetic experiments, and check counts were not independently reproduced for this compilation. Private code paths are not published, and the snapshot is not promoted to a current specification.
4. *Agent Working Event Chain Mapping Audit*, 2026-11-05. Used for the boundary between Hongchenxian and the empiricist project. It cites excerpts from *Dual Top-Level Knowledge Graph and Connection Graph Architecture v1.1* (2026-09-20). The full original specification was not obtained for this compilation, so it cannot be described as fully verified.
5. Latest local source and experiment inventory confirmation received during release preparation, 2026-11-06. It confirms 65 source files and T1–T10 synthetic experiments; an isolated candidate is under review. T10 has 50/50 receipts and an existing report, including results below expectations. This is an inventory/status update, not independent reproduction or evidence that every experiment succeeded.

The glossary version visible in this review was v0.57. It is the latest verifiable version within the materials reviewed, not a global certification of the latest version of all local engineering materials. Where the October 22 draft overlaps with explicit corrections from November 2, the later clarification describes the current concept, while earlier candidates retain their status as designs.

## Public technical references

- [Attention Is All You Need](https://arxiv.org/abs/1706.03762): a conventional technical starting point for Q/K/V and FFNs. Its results do not establish this project's two-forest, combination, or revision capabilities.
- [Official jieba repository](https://github.com/fxsjy/jieba): listed in the original design as a candidate Chinese tokenization tool. Actual adoption requires a separate review of the version, license, dictionary, model, and HMM configuration used.
- [NLTK tokenization interfaces](https://www.nltk.org/api/nltk.tokenize.html): listed in the original design as a reference for whitespace splitting and span preservation in suitable writing systems. Listing the link does not claim installation, testing, or adoption.

These are public reference links only. No code, dictionaries, models, or paper content have been copied. This compilation makes no third-party licensing guarantee and does not select a project license.

## Editorial changes

This compilation adds a README, proposal digest, evidence mapping, and source notes, with complete Chinese and English counterparts and the requested The Abyss entry title and theoretical proposition. It does not modify original materials. Neither the full glossary containing private discussion nor the historical snapshot containing absolute computer paths is copied. The digest retains necessary algorithmic directions, later corrections, and uncertainty, while omitting personal forms of address, identities and accounts, message identifiers, private locations, and material unrelated to the technical preview.

Any later source-code supplement must recheck current authoritative engineering sources, versions, dependencies, and third-party licenses, and provide execution and acceptance evidence matching its claims. Merely rewriting this description as “implemented” is insufficient.
