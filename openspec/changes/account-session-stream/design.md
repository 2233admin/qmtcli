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
claim replacement of the whole SDK. Native worker reuse is now implemented; MCP reuse is
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
- At the four-section milestone, SDK start/connect/subscribe reused one account connection. Each snapshot's
  native work used a separate isolated child session (superseded below); do not report one total
  transport session for the hybrid path.
- Full regression: 364 passed; ruff, whitespace checks and new native module C901
  complexity checks pass. Protocol phases were split after C901 found feed=14.
- Final raw acceptance binds all five implementation source hashes in private
  qmtcli-four-section-stdio-live.json; query values/account IDs are not committed.
- Real account event activity was absent; no claim of real push/reconnect validation.
- Updated Code Intel normal passed for the native trade extension; receipt directory
  1793472238440-42372-core under the same local artifact root.


## Persistent native follow-up (2026-11-01)

- NativeSession uses the standard-library subprocess/queue/threading ownership pattern,
  without a dependency or network server. One child owns native C++ objects and queue
  mappings for repeated sequential reads. Existing one-shot commands stay compatible.
- Every operation allocates new application IDs and wire sequences. No result cache,
  hidden replay or SDK fallback. Wrong IDs, EOF/crash, missing replies and protocol
  failures close the child. A later request can start a new generation. Only the
  Popen-owned worker tree may be terminated during bounded cleanup; never QMT.
- Passive SDK delivery trace observed a trade request and three server replies of
  552 bytes with the final flag. The Python native callback was never invoked while
  the asset control callback arrived. Loss is localized to native SDK receive/dispatch
  before Python; the exact internal binary defect is not established. Rebinding a
  Python wrapper did not fix it. Evidence: qmtcli-sdk-trade-delivery.json.
- Real Python 3.14 JSONL driver -> SDK-compatible server: ten complete snapshots,
  SDK generation stable and native generation=1 throughout; every native trade
  joined to SDK orders by account/security/system ID and passed direction/quantity
  checks. EOF exit=0. First collection 304.796ms; subsequent nine 44.922–47.130ms.
  First uses SDK asset/native trades; warm samples use native asset/trades. This is
  a local sample, not a controlled speedup ratio or production percentile.
- Private receipt qmtcli-persistent-native-live.json is under the existing research
  recovery/five-areas directory and binds six implementation source hashes. It was
  rerun after the final code change; final values supersede samples above if different.
- Synthetic public JSONL tests check fresh responses, reuse, account switching and
  EOF release. Wire tests check one handshake, advancing sequences and stale reply
  rejection. Child crash/timeout/wrong ID tests verify failure without automatic replay;
  forced cleanup test mocks taskkill and asserts only the owned PID is targeted.

| Conclusion | Verification | Result and limit |
|---|---|---|
| Native reuse and fresh reads | pytest; real ten-snapshot JSONL script | Pass; pinned MiniQMT build/current account only |
| Complete four-section snapshots | Real JSONL, native trade/SDK order cross-check | Pass; sequential, non-atomic; SDK required for positions/orders |
| Real event/recovery consistency | No live trade/disconnect generated | Not verified; requires actual callbacks and controlled recovery observations |

Main worktree user changes preserved. This branch remains in_review, unmerged,
with principal acceptance and the native asset base acceptance outstanding.

Final checks: 373 pytest tests passed; ruff general and C901 native-module checks
passed. An initial Code Intel run detected edits made while it was consuming the
source manifest and failed snapshot consistency (1793479842464-37784-core). The frozen-tree rerun passed: 1793479955478-2480-core/run-complete.json under the same artifact root.

## Extended recovery and sustained-read acceptance (2026-11-01)

No production implementation changes in this follow-up. Tests and receipts extend
coverage of dd9d8dc. All scripts use only account queries, and crash tests terminate
only handles returned by the test session's own Popen, never shared MiniQMT processes.

| Conclusion | Verification | Result and limit |
|---|---|---|
| Sustained complete snapshots | verify-qmtcli-100-snapshots.py, actual JSONL server, no query mocks | 100/100 complete; native generation=1; every trade checked against SDK orders; server exit=0 |
| Native worker restart | verify-qmtcli-native-recovery.py under Python 3.14 | 21 reads on one worker; 3 idle-worker deaths each recovered on next read; write-boundary crash rejected current read and next read recovered |
| Deadline failure | Same real native recovery script | Startup deadline deliberately expired; error and cleanup, later query succeeded; observed failure/cleanup 225.320ms, not a process-level microsecond hard deadline |
| Owned resource release | Same script plus final process inventory | All recorded owned workers exited; 0 recorded owned reply paths remained; no qmtcli server/native worker found after public tests; this is not a memory-leak proof |
| Wrong-account isolation/recovery | verify-qmtcli-invalid-account-recovery.py, Python 3.14 public native JSONL | Normal/wrong/normal produced success/error/success with correct IDs; wrong account had no data; successful replies matched requested account |
| Invalid child replies | test_invalid_worker_output_rejects_read_then_recovers | Malformed JSON, non-object envelope, boolean ID, non-object data, explicit failure all reject current request without replay; later request starts new generation |
| Full regression | uv run --no-sync --extra dev pytest -q; ruff check . | 378 passed (3.81s); ruff passed, exit=0 |
| Broker event/reconnect behavior | No broker disconnect or trade event induced | Still not verified. Worker restart is not broker reconnect; no claim of real incremental consistency |

Timing: first snapshot 263.498ms; 99 warm collection samples min=29.950ms,
median=61.279ms, max=91.827ms. Total server run 6789.424ms including startup/EOF.
Cold sample uses SDK asset/native trades; warm samples use native asset/trades with
SDK positions/orders. These samples show variability, not a fixed 45ms contract.

Private sanitized receipts remain under the existing recovery/five-areas directory:
qmtcli-100-snapshots-live.json, qmtcli-native-recovery-live.json and
qmtcli-invalid-account-recovery-live.json. Real account values/IDs are never committed.
Shared XtMiniQmt/miniquote remained responsive. Work stays in_review/unmerged.
