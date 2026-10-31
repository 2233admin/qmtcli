# Work and verification

- [x] Regression tests for reuse, snapshot shape/failure, account isolation and cleanup.
- [x] SDK callback adapter, owned session lifecycle and server reuse.
- [x] Snapshot discovery/CLI/RPC/MCP and optional native asset source.
- [x] Incremental account event subscription, disconnect generation and EOF cleanup.
- [x] Full pytest, ruff, parseable examples and before/after connection receipt.
- [x] Record live verification or its concrete limits; inspect changes and owned processes.

Implementation checks: 364 tests pass, ruff and diff whitespace checks pass.
These checkboxes record completed engineering checks, not principal acceptance or
full live event/reconnect validation. See design.md for the live limit and receipts.

- [x] Follow-up: native trade request/decoder and strict nonempty/empty/error distinctions.
- [x] Follow-up: actual JSONL two complete four-section snapshots, unsubscribe and clean EOF.
