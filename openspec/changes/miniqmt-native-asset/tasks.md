# Tasks

- [x] Fetch latest upstream, isolate worktree, run baseline tests (287 passed).
- [x] Verify connect/account/asset layouts using offline fake SDK data objects.
- [x] Write failing protocol and CLI contract tests.
- [x] Implement pure codecs and version-pinned native queue adapter.
- [x] Verify isolated native queue round-trip before any live IPC request.
- [x] Integrate native backend across CLI/RPC/discovery and document limits.
- [x] Run offline suite and lint; perform sanitized live asset check.
- [x] Review changed comments and evidence.
- [x] Prepare implementation branch for principal review; remote delivery is
  recorded in the final handoff.

Validation: 320 offline tests passed with the existing dev environment, ruff
passed, diff whitespace checks passed. Local Python 3.14.7 live CLI/RPC/JSONL
queries matched all six fields of a reference SDK query; no xtquant module was
imported by that Python 3.14 process. Raw financial data is not committed.

Limits: one pinned MiniQMT build and STOCK account type; no big-QMT claim,
persistent native sessions or additional account/data commands. Native DLL
diagnostics are isolated from the public JSON transport.
