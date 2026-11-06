# Candidate scope and scanning limits

[简体中文](EXCLUSIONS.md)

Thirty-two `.mjs` files were selected from one sealed candidate, with preview documentation and verification scripts added. The Abyss section adds four Chinese/English pairs of technical summaries. The full glossary containing private discussions and historical originals with private paths are excluded. The original working directory was not copied wholesale.

Excluded: the official plugin/launchers and Python runner; raw public-source excerpts; server configuration and readouts; historical transfer scripts/tar/b64 packages; account directories; real databases/WAL/SHM; real member memory; original model replies; email/chat records; personal information; private links.

The candidate scan checks common secret formats, private paths, account/host identifiers, email, IP addresses, sensitive file types, symlinks, and static import closure. It reports only locations/categories, never matched values. A precise reviewed exception covers intentionally fake header values in synthetic tests; unknown values remain findings.

The scan is heuristic and cannot prove the absence of every secret or third-party rights issue. Hashes establish byte consistency with this inventory, not code security. The scan does not read parent directories, original credential directories, or real datasets. Any later addition requires renewed scanning, tests, and a refreshed manifest.
