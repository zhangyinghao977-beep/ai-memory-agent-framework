# Third-party sources and license scope

[简体中文](THIRD_PARTY_NOTICES.md)

## DeepSeek Harness

- Project: https://github.com/deepseek-ai/deepseek-harness
- Reviewed license: https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE
- Reviewed notices: https://github.com/deepseek-ai/deepseek-harness/blob/master/THIRD_PARTY_NOTICES.md
- Review date: 2026-11-06. The public master root license is MIT, with `Copyright (c) 2026 DeepSeek`.
- The displayed page did not establish a verifiable fixed commit for this review. This records the terms currently shown on that public page; it does not establish terms for every earlier version or dependency, or equivalence between installed rc.5 and master.

Some project boundary checks and doubles were written with reference to the public interfaces and data formats, particularly `catalog-policy.mjs`, `protected-wire.mjs`, `provider-double.mjs`, and `sdk-runtime-double.mjs`. This preview does not include raw upstream source excerpts, official SDK packages, upstream vendored libraries, or their third-party dependencies. To preserve provenance and any applicable upstream notice, [DeepSeek-Harness-MIT.txt](third_party/DeepSeek-Harness-MIT.txt) separately records the reviewed MIT text. It does not select a license for The Abyss or Hongchenxian.

Upstream notices also list dependencies with their own terms. An MIT root license does not make every dependency MIT. Bundling any upstream runtime package later requires a fresh review of the complete dependency closure and notices for the exact package version.

## Project-local vendor copies

`projects/hongchenxian/research/central-step/vendor/` contains source snapshots of earlier Hongchenxian modules, not npm-installed packages. Their bytes and sealed-package provenance are recorded in `evidence/SOURCE_MANIFEST.json`. Traceable files do not by themselves establish every author's rights. The project license and contribution attribution still require the owner's decision.

## Node.js / SQLite

The preview uses separately installed Node.js built-ins, including the SQLite binding. It does not redistribute Node or SQLite binaries/source. The WAL-format checker implements the limited format validation required by the project; SQLite source is not bundled. Node/SQLite licenses come with their original distributions and do not select this project's license.

## The Abyss research source and references

The Abyss now includes selected source from the original local research working tree in [implementation](projects/the-abyss/implementation/): 65 core `.py` files, 25 `test_*.py` files, and 31 experiment `.py` files (including helpers), plus 11 plan configurations for fresh runs. It includes the memory foundation, evaluation utilities, and T1–T10 controlled synthetic experiments, in addition to the theory summaries. [SOURCE_SNAPSHOT.json](projects/the-abyss/implementation/historical/SOURCE_SNAPSHOT.json) records relative source names and hashes at inspection. That inventory does not establish authorship, ownership, or the code version executed in historical experiments; see [NOTICES.md](projects/the-abyss/implementation/NOTICES.md) for candidate edits and evidence boundaries.

A public license for the project code has not been selected. Inclusion does not grant an open-source license or certify complete provenance; see [LICENSE-STATUS.md](projects/the-abyss/implementation/LICENSE-STATUS.md). Runtime dependencies are installed separately by readers. Their implementations are not bundled, and their licenses do not select the project's license.

The theory documents retain public reference links to the Transformer paper and possible tokenization tools without copying paper text, third-party code, dictionaries, models, or weights. External-material adapters and the retired toy task are excluded. T1–T10 generate synthetic data and do not depend on the optional 119M backbone or historical corpus collection.

Historical comments in the optional 119M integration path describe a backbone reimplementation based on a kernel from another research branch. The exact source-kernel version, its license, a public weight URL, and a complete public retraining procedure remain unresolved; that provenance must not be presented as verified, wholly independent original work. Historical large-corpus processing also depends on an existing `corpus_index.sqlite`; this review did not find a complete program to rebuild it from downloaded Parquet files. Including synthetic-experiment source does not resolve these limitations.

Third-party corpora, lexicons, tokenizer artifacts, weights, databases, and original run receipts are not bundled. See [data sources](projects/the-abyss/implementation/docs/DATA_SOURCES.en.md) for acquisition guidance, separate recorded terms, and unverified steps. This preview also excludes NRC EmoLex originals and derived lexicon copies subject to its redistribution prohibition. Publicly discoverable sources do not establish reproducibility of the complete historical pipeline. No dependencies were installed and no tests or training were run during The Abyss source preparation.
