# Third-party sources and license scope

[简体中文](THIRD_PARTY_NOTICES.md)

## DeepSeek Harness

- Project: https://github.com/deepseek-ai/deepseek-harness
- Reviewed license: https://github.com/deepseek-ai/deepseek-harness/blob/master/LICENSE
- Reviewed notices: https://github.com/deepseek-ai/deepseek-harness/blob/master/THIRD_PARTY_NOTICES.md
- Review date: 2026-11-06. The public master root license is MIT, with `Copyright (c) 2026 DeepSeek`.
- The displayed page did not establish a verifiable fixed commit for this review. This records the terms currently shown on that public page; it does not establish terms for every earlier version or dependency, or equivalence between installed rc.5 and master.

Some project boundary checks and doubles were written with reference to the public interfaces and data formats, particularly `catalog-policy.mjs`, `protected-wire.mjs`, `provider-double.mjs`, and `sdk-runtime-double.mjs`. This preview does not include raw upstream source excerpts, official SDK packages, upstream vendored libraries, or their third-party dependencies. To preserve provenance and any applicable upstream notice, `third_party/DeepSeek-Harness-MIT.txt` separately records the reviewed MIT text. It does not select a license for The Abyss or Hongchenxian.

Upstream notices also list dependencies with their own terms. An MIT root license does not make every dependency MIT. Bundling any upstream runtime package later requires a fresh review of the complete dependency closure and notices for the exact package version.

## Project-local vendor copies

`projects/hongchenxian/research/central-step/vendor/` contains source snapshots of earlier Hongchenxian modules, not npm-installed packages. Their bytes and sealed-package provenance are recorded in `evidence/SOURCE_MANIFEST.json`. Traceable files do not by themselves establish every author's rights. The project license and contribution attribution still require the owner's decision.

## Node.js / SQLite

The preview uses separately installed Node.js built-ins, including the SQLite binding. It does not redistribute Node or SQLite binaries/source. The WAL-format checker implements the limited format validation required by the project; SQLite source is not bundled. Node/SQLite licenses come with their original distributions and do not select this project's license.

## The Abyss references

The Abyss documents retain public reference links to the Transformer paper and possible tokenization tools. No paper text, third-party code, dictionary, model, or weights are copied into the theory summaries. A possible future dependency is not an adopted or license-cleared dependency. Reviewed local-source integration must be assessed separately before inclusion.
