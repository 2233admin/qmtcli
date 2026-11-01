# Work and verification

- [x] Regression tests for reuse, snapshot shape/failure, account isolation and cleanup.
- [x] SDK callback adapter, owned session lifecycle and server reuse.
- [x] Snapshot discovery/CLI/RPC/MCP and optional native asset source.
- [x] Incremental account event subscription, disconnect generation and EOF cleanup.
- [x] Full pytest, ruff, parseable examples and before/after connection receipt.
- [x] Record live verification or its concrete limits; inspect changes and owned processes.

Implementation checks: 427 tests pass, ruff and diff whitespace checks pass.
These checkboxes record completed engineering checks, not principal acceptance or
full live event/reconnect validation. See design.md for the live limit and receipts.

- [x] Follow-up: native trade request/decoder and strict nonempty/empty/error distinctions.
- [x] Follow-up: actual JSONL two complete four-section snapshots, unsubscribe and clean EOF.


- [x] Persistent native worker reuse, fresh wire sequence tests and real ten-snapshot acceptance.
- [x] SDK delivery loss localized before Python callback; exact vendor defect remains unresolved.

- [x] Extended real worker-death/deadline recovery, wrong-account JSONL recovery and 100 complete snapshots; raw receipts retained.
- [x] Invalid worker output rejection/recovery regression cases; 378 tests pass.

- [x] Native position/order codecs and server cancelable filtering, with actual SDK public-field comparison.
- [x] Fully native CLI/JSONL snapshots under Python 3.14 with xtquant import forbidden; invalid-account recovery and EOF.
- [x] Agent/MCP discovery, examples, docs and 400-test regression for this extension.

- [x] Research-only native quote RPC snapshot, subscription lifecycle and history probes on Python 3.15.2, with frame negative controls and real supply failure notification.
- [ ] Formal QMTCLI native market integration, live market push and auction semantic acceptance (not established by the probe).
  - [x] Formal native full-tick snapshot CLI/RPC/JSONL/MCP integration with explicit backend.
  - [x] Python 3.15.2 entry-point acceptance against SDK 3.11; no xtquant imports or compiled BSON.
  - [ ] Persistent native quote connection, history decoding, live push and auction semantics.

- [x] Actual maintenance: full existing daily backup, 5579-code verification, 5571 at target date, 5566 complete eight-session coverage.
- [x] Two-stock minute/tick updates and real 10-30 auction readback; exception CSV and independent freshness/numeric checks.
- [ ] Resolve/classify 13 symbol-specific calendar gaps; batch/native download lifecycle remains under review.

- [x] Rust direct full-tick experiment: library/exe, actual PID, no Python/broker DLL runtime dependency.
- [x] Two-stock official SDK control, real SH/SZ 51,196-record read and exact vendor BSON comparison.
- [x] Ten Rust tests, Clippy/fmt, existing 427 Python tests and Code Intel structural gate.
- [ ] Strict market-wide SDK JSON absolute-float parity: six values exceed 1e-12 by one ULP; retained as a failed extra check.
