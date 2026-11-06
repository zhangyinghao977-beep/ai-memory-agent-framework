# Evidence levels and known gaps

[简体中文](EVIDENCE.md)

## This preview

The source baseline is `hcx-central-step-abi-20261106-v04`, whose archive SHA256 is `f8a1d1675f8b98d715a811d1e34e3f6defaad5677a1ac97d5721f01b53a2139a`. The allowlist includes 32 code files: 30 unchanged and two preview-isolation changes. Their current locations are recorded in the repository-root `evidence/SOURCE_MANIFEST.json`.

The final rerun belongs in the repository-root `evidence/VALIDATION.json`. Of the original 70 Node cases, 69 are retained; one is replaced with a check that this preview cannot load the official SDK. New network-guard tests are counted separately. Not every test is byte-identical to the original package. The original 36 Python mock/static runner tests are excluded from this minimal preview and are not counted as its results.

## Historical results, summaries only

- Central-step v04: 70 local SDK-double Node tests and 36 Python tests passed. Its official five-case/ten-worker matrix was not executed; the installed-version metadata gate remained closed.
- Policy a04 and native-index a03: retained official synthetic passes for migration and native-tool/read contracts. They do not prove recovery of real members.
- Rolling a03: the first worker completed 17 synthetic streams, then the runner failed at raw-prefix capture. The full matrix failed/remained incomplete; reopen and subsequent cases were not run.
- Real-pool short run: seven spent requests, five accepted settlements, two missing receipts, and three members making no request. The run failed and original state was retained. Continuous real sleep/wake/stop, same-identity recovery, and the 72-hour objective remain incomplete.

These are publication-oriented summaries of earlier reviewed records. This preview does not include original experiment logs, server identifiers, or real content. Readers cannot independently verify all historical experiments from these summaries alone. Publishing original evidence would require separate de-identification and authorization.

## Not yet demonstrated

Real SDK serializer/SSE behavior, installed-version compatibility, trusted host source custody and writer exclusion, cryptographic member authentication, append-only migration of original identities, real ten-member collaboration, real costs, production durability, and at least 72 hours of continuous operation.
