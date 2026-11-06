# Dependencies and reproduction environment

[简体中文](DEPENDENCIES.md)

- Verified: Linux, Node.js 24.22.1. `.nvmrc`, `.node-version`, and `engines.node` pin that version at the repository root.
- Runtime and tests use only Node built-ins, including `node:sqlite`, Web Response/Headers, AbortSignal, and the test runner.
- There are no npm dependency or devDependency entries. The lockfile has no package download entries, registry addresses, or authentication configuration. `npm install` is unnecessary.
- This preview neither installs nor bundles DeepSeek Harness, Cordis, model SDKs, Python, database binaries, or a Node distribution.
- Default `npm test` loads the local accidental-network-call guard before research tests. Public provider URLs remain only as constants checked by the serialization contract; the injected forward function returns a synthetic Response.
- Only the exact environment above has been verified. No compatibility claim is made for other Node 24 minor versions, Windows, or macOS.
- Any future SDK, CI action, or npm dependency requires a fixed version/commit and renewed review of licenses, dependency closure, network access, and secret exposure.
