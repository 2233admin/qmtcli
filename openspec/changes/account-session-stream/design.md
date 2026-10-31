# Design and source contracts

Use the existing XtQuantTrader lifecycle and callback API, verified in the installed
xtquant/xttrader.py: register_callback before start, subscribe(account), stop(). stop()
waits for callback executors, so callback threads only mark disconnection; the server
request owner performs cleanup/reconnect. Do not stop from inside a callback.

A small AccountSession owns one active gateway, keyed by requested path/account/type
and subscription mode. Avoid a global unbounded pool or result cache. Generation
and a lock coordinate callback publication; the synchronous request loop owns SDK
creation/query/close. No network listener or new dependencies. Reuse SDK lifecycle
rather than a new transport framework; local code only adapts it to JSONL ownership.

Snapshots perform four sequential current queries, not an atomic broker snapshot.
Sequence bounds expose overlap with delivered events. They do not implement an
authoritative materialized portfolio or deduplicate/reorder broker events.
Unsubscribe disables account JSONL forwarding; the account remains connected for
subsequent queries. Switching account ends the previous subscription.

Native asset and trades remain crash-isolated and version-pinned. Do not infer native
position/order codecs from internal C++ structures. A snapshot explicitly chooses
asset/trade backends and annotates both. Both native sections share one worker;
positions/orders use the retained SDK session. This change extends the previous
asset-only allowlist with read-only trade request 20007; trading writes stay blocked.

## Verification receipt (2026-11-01)

- Initial four regression tests failed for repeated connect, missing snapshot,
  account switch cleanup and failed snapshot recovery. The implementation passes
  those plus lifecycle, callback, isolation, deadlines and malformed-request checks.
- `uv run --no-sync --extra dev pytest -q`: 350 passed. Existing F:/projects/qmtcli/.venv
  reused via UV_PROJECT_ENVIRONMENT without syncing/modifying dependencies; pytest
  imports this worktree's src via repository configuration. Python 3.14 global
  environment was also used during development through uv --no-project.
- `uv run --no-sync --extra dev ruff check .` and `git diff --check`: pass.
  New AccountSession also passes ruff C901 complexity check.
- Actual JSONL dispatcher with synthetic gateway: same forty queries, forty new
  reads, connection creation 40 -> 1, final stop=1. Real gateway + fake SDK verifies
  register/start/connect/subscribe/stop each once. No claimed latency multiplier.
- Installed SDK source verified register_callback/start/subscribe/stop and the
  four public async query methods. Its synchronous method waits on Future.result()
  without a deadline; snapshot now uses async replies and one shared response budget.
- Python 3.14 launched a compatible Python 3.11 live worker. Asset, positions and
  orders returned on two attempts; four asset values were finite. Trade replies
  did not arrive. Snapshots correctly returned explicit deadline errors around 5s,
  with two connects/two clean stops due to invalidation. That SDK-only live snapshot failed.
  No forced disconnect or actual trade event was
  generated; real reconnect/event interleavings remain unverified.
- Live capture contains source hashes before the final malformed-command envelope
  guard; that final fix only concerns invalid JSON command types and is covered by
  the final full test run. Financial values and account identifiers stay out of repo.
- Code Intel normal completed before and after implementation. Local final analysis:
  C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/
  1793470759035-68340-core/run-complete.json. No second planning system was created.
- Private raw receipts remain under F:/projects/_research/qmt-ida-20261031/recovery/
  five-areas/qmtcli-session-baseline.json, qmtcli-session-after.json and
  qmtcli-account-session-live.json. No SDK verification worker remains running.

## Remaining acceptance

SDK-only trade callbacks still fail on the tested environment. The native backend
now completes this deliverable; native positions/orders, actual trade events and
real recovery interleavings are separate remaining capabilities. This does not
claim persistent native worker reuse or replacement of the whole SDK. MCP reuse is
within one snapshot. Main working files remain untouched; the branch depends on
the still-unaccepted native asset base change.

## Four-section acceptance completed (follow-up)

- Initial empty-trade hypothesis was disproved: actual native reads returned nonempty
  trades. A passive empty-branch probe hit neither expected error site. That probe
  did not establish the SDK's internal failure cause. Do not keep the discarded
  hypothesis as the diagnosis.
- Added native_trades.py using the existing ringbuffer transport. Asset validation
  precedes trade query in the same worker. No account -> explicit error. The pinned
  service's -1 after a validated account/no partial rows is the explicit empty-list
  branch; missing replies always time out. Service fingerprint is additionally pinned.
- Nonempty 552-byte StockTrade rows are decoded into SDK public field names, with
  numeric/account checks and strict 38-byte fragment envelope offset/length validation.
  Unit tests cover multiple rows/fragments, invalid frames, unknown accounts, wrong
  sessions, partial failure, timeout and no duplicate query on intermediate fragments.
- Public asset/trades native commands remain SDK-free. The native trade API was
  actually exercised by Python 3.14, including a wrong-account negative control.
- Actual JSONL CLI acceptance (no SDK/query mocks): subscribe; snapshot with SDK
  asset/native trades; snapshot with native asset/native trades; unsubscribe; EOF.
  Both snapshots returned every section as valid JSON, finite asset/trade values,
  and the same SDK connection generation. Process exit=0. Latest collection samples
  were 272.221ms and 272.203ms; these are two samples, not a percentile or speedup.
- Cross-check against SDK orders also passed for every returned trade: account,
  security and order_sysid association, direction and volume bounds. An initial
  numeric-order-id join failed because both paths returned nonunique zero IDs;
  its private negative receipt is retained. Do not invent missing numeric IDs.
- SDK start/connect/subscribe still reuse one account connection. Each snapshot's
  native work uses a separate isolated child session; do not report one total
  transport session for the hybrid path.
- Full regression: 364 passed; ruff, whitespace checks and new native module C901
  complexity checks pass. Protocol phases were split after C901 found feed=14.
- Final raw acceptance binds all five implementation source hashes in private
  qmtcli-four-section-stdio-live.json; query values/account IDs are not committed.
- Real account event activity was absent; no claim of real push/reconnect validation.
- Updated Code Intel normal passed for the native trade extension; receipt directory
  1793472238440-42372-core under the same local artifact root.
