# Observable acceptance

- Forty same-account JSONL queries use one connect and one account subscription;
  each still queries fresh data. Switching account/path/type closes the old session.
- account-snapshot returns asset/positions/orders/trades using one retained SDK connection and, when selected, one native connection,
  collection timestamps and an explicit non-atomic marker; query failure is an error.
- Account subscription forwards original SDK asset/position/order/trade/status and
  disconnect callbacks as JSONL with generation/sequence; no polling or fabricated data.
- Disconnect invalidates the session. The next request reconnects; no hidden retries.
  Events from closed/replaced generations are suppressed. EOF closes owned SDK state.
- Snapshot asset_backend=native and trades_backend=native reuse a single pinned
  native worker when both are selected; positions/orders still require the SDK.
  Native trade frames support nonempty rows, fragments, explicit empty completion
  after account validation, wrong-account rejection and deadlines without guessing.
  Modern agents can drive a compatible-runtime
  server over JSONL without importing xtquant. No claim of full SDK replacement.
- Existing commands/envelopes/discovery remain compatible; pytest and ruff pass.
- Compare connection counts and controlled overhead separately from real latency.
- Actual JSONL server must return all four sections twice for the current account,
  preserve the SDK session generation and exit cleanly after unsubscribe/EOF.

Follow-up efficiency acceptance:
- JSONL server retains one native worker/handshake for repeated same-account reads.
  Each request still reads fresh wire responses; no account result cache.
- Native request IDs, wire sequences and native generation distinguish replies.
  Timeout/crash/malformed reply fails that request and closes its owned process;
  a later request may start a fresh worker, without hidden replay.
- SDK/native account switching and EOF close owned native workers. Constant native
  memory/queue ownership is scoped to one active account per native backend.
- Benchmark first and warm complete snapshots on the real JSONL boundary; report
  samples and counts without extrapolating to unmeasured p95 or whole-system speed.

## Native positions/orders extension

Authorized next slice: native read-only positions and orders, then fully native
four-section snapshots on Python 3.14. Reuse the existing pinned queue/session path.
Acceptance: public CLI/JSONL/MCP discovery, strict framing/empty/error behavior,
SDK/native field-by-field comparison, server reuse and EOF cleanup. Keep backend
selection explicit and preserve SDK defaults; no trading writes or invented fields.
Sources: pinned XtQuantServer dispatch 0xEF90 (20006 order, 20008 position), response
wrappers 0x11450 (476 bytes), 0x11490 (328 bytes); OrderService_mini query handlers
0x13A7B0/0x13E890 and record writers 0x11AAD0/0x11BD30. Reverify live output before
claiming codec correctness. Existing wheel is the owned ringbuffer runtime adapter;
new custom code is limited to protocol codecs and routing, no replacement transport.
