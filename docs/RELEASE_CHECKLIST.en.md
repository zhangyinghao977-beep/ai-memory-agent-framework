# Integration release checklist

[简体中文](RELEASE_CHECKLIST.md)

## Prepared

- Retained bilingual theory and provenance documents under `projects/the-abyss/`, with selected research sources and adaptations added under [implementation](../projects/the-abyss/implementation/README.en.md): 65 core Python files, 25 `test_*.py` files, 31 experiment Python files including the shared helper, and 11 plans.
- Included Abyss dependency configuration, new-run entry points, a source snapshot, and historical synthetic-result summaries. These describe installation requirements, code, provenance, and historical evidence separately, not current execution validation. T10's failed S2 and unseen-package generalization problem remain explicit.
- Abyss checks are [static only](../projects/the-abyss/implementation/STATIC_CHECKS.json): no dependency installation, project imports, pytest, training, or independent reproduction. The 12 foundation contract-test files and optional `test_t1.py` are explicitly named lightweight candidates only; other tests include training and T4 subprocess fault injection.
- Preserved the allowlisted Hongchenxian source, offline tests, runtime requirements, and prior evidence. The earlier 72/72 belongs only to the Hongchenxian checkpoint, not Abyss acceptance.
- Preserved the scope of Hongchenxian's removed deployment entry points, refusal to load official SDKs, and preparation locks. Its source is unchanged in this integration.
- Real data, account material, and raw operational logs excluded.
- Local doubles, official synthetic runs, real experiments, failures, and unexecuted scope reported separately.

## Commit scope and limits on later claims

1. Before committing, refresh repository-wide `SHA256SUMS`, links, and scans against the final tree. Add [ABYSS_INTEGRATION.json](../evidence/ABYSS_INTEGRATION.json) for this stage; retain the original scope of `VALIDATION.json`, `SCAN_REPORT.json`, and `SOURCE_MANIFEST.json` instead of retroactively treating old results as validation of new code.
2. The rights holders still need to determine the original code's license and author/contributor attribution. There is no project LICENSE; source inclusion does not automatically grant an open-source license.
3. Keep this preview limited to selected code, configuration, and summary evidence, not the full original workspace. Real sessions, original corpora, weights, databases, and raw receipts are not included.
4. Before claiming that The Abyss installs, runs successfully, or has been independently reproduced, perform the corresponding execution validation separately. Current adaptations prepare new runs; migration of existing run directories or weights is unverified and may retain internal paths.
5. Retain the gaps in the [material-source notes](../projects/the-abyss/implementation/docs/DATA_SOURCES.en.md), including provenance/licensing for the optional 119M backbone and from-scratch `corpus_index.sqlite` generation. Download instructions do not establish reproduction of a complete material pipeline. T1–T10 synthetic experiments do not depend on these external materials.
6. The existing upstream-license review concerns the master page recorded at the time, which did not identify the exact historical source commit; it is not proof of installed rc.5 equivalence. Third-party materials remain unbundled and separately licensed.
7. npm, CI, or real-SDK publication adds dependency and execution scope. This copy has no automatic-publishing configuration.

One repository with distinct project areas has been selected. This integration adds selected source and historical summaries to The Abyss's theory entry point, while remaining an unfinished memory-and-learning research preview. It is not a distribution of the complete local workspace, a complete product, validation of the entire theory, or a license grant.
