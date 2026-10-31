# Observable acceptance

- Forty same-account JSONL queries use one connect and one account subscription;
  each still queries fresh data. Switching account/path/type closes the old session.
- account-snapshot returns asset/positions/orders/trades with one connection,
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
