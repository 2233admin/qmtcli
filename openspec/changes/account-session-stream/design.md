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
positions/orders use the retained SDK session in the section-backend mode. Fully native mode now reads all four in one native worker. This change extends the previous
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

SDK-only trade callbacks still fail on the tested environment. Fully native account snapshots now pass on the pinned build; actual trade events and
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

## Fully native positions/orders and snapshots (current extension)

[K, static] Pinned XtQuantServer dispatch at 0xEF90 routes 20006 to order query and
20008 to position query. Its response wrappers 0x11450/0x11490 send 476/328 bytes.
Pinned OrderService_mini writers 0x11AAD0 and 0x11BD30 establish field offsets; the
latter was newly decompiled from the existing database into the private research
native-position-codec.c. Query handlers 0x13A7B0/0x13E890 establish the order-ID,
server cancelable bit (+36), symbol filtering and explicit empty/error paths. The
installed xttrader.py/xttype.py and actual SDK objects define canonical public fields.

Implementation: native_records.py decodes only canonical public position/order
fields with account/type, numeric and quantity validation. The existing reply
collector now accepts kind/size/decoder parameters, preserving trade defaults and
strict fragmentation/empty rules. One native operation validates the account's
asset first; full snapshots then query positions, orders and trades with new wire
sequences on the same worker. Only read requests 20006/20008 extend the allowlist.
Server-side cancelable filtering is used; client status heuristics are not added.

Public contract: positions/orders accept backend=native. account_snapshot and CLI
account-snapshot accept backend=native to select all four sections and bypass SDK
initialization (including inherited xtdc token). backend=sdk remains the default;
asset_backend/trades_backend apply only to that legacy section-selection mode.
The full-native meta annotates every section and native_generation; SDK event
cursor fields remain distinct and have initial values in a native-only session.
There is no native event subscription or atomic snapshot promise.

An initial mapping of an extra avg_price field failed actual SDK comparison because
that field is not exposed by this SDK. It was removed, not relabeled or guessed.
The private negative receipt qmtcli-native-records-extra-field-rejected.json is
retained. Final public fields match; no m_* duplicate SDK aliases are synthesized.

| Acceptance | Verification | Result and limit |
|---|---|---|
| Canonical position/order fields and cancelable filtering | verify-qmtcli-native-records.py vs real SDK async queries | All returned canonical fields and identity sets matched for nonempty positions, orders and cancelable orders; no generated transaction |
| Fully native public JSONL | verify-qmtcli-fully-native.py, Python 3.14.7 import guard forbids xtquant | 21 successful full snapshots plus invalid-account error and subsequent valid recovery; persistent generation on repeated same-account reads; clean EOF |
| Public CLI | Same script, separate real positions/orders/account-snapshot CLI processes | Passed under the same SDK import guard; canonical fields compared against SDK reference |
| Full snapshot contents | Same JSONL script | Assets compared to SDK within numeric tolerance; positions/orders every canonical field; native trades linked to orders by account/security/system ID and quantity/direction |
| Wire/error contracts | test_native_records.py, test_native_account_cli.py plus existing trade/session regressions | Strict record sizes, account/type checks, nonfinite values, large int64 quantity, fragments, explicit synthetic empty lists, exact query sequence, invalid budget/filter rejection and MCP backend discovery |
| Regression | uv run --no-sync --extra dev pytest -q; ruff check .; ruff native modules --select C901 | 400 passed; general lint and native complexity checks passed |
| Live empty-account/events/reconnect/build coverage | No suitable empty account or real trade/disconnect induced | Unverified: real empty position/order lists, native push, broker reconnect, other account types, big QMT and other build fingerprints |

Final live receipt qmtcli-fully-native-live.json binds six implementation source
hashes; raw financial values stay only in test process memory. Latest 21 collection
samples: min 43.920ms, median 46.269ms, max 274.936ms including cold/recovery samples.
This is not a controlled before/after speedup measurement. Existing hybrid/SDK
behavior remains covered by full regression. No new dependency, network server,
trading write, QMT installation, or shared-client restart was introduced.

Code Intel normal on the frozen extension tree passed (exit=0):
C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/
1793483704357-77740-core/run-complete.json. Parseable JSONL/examples and MCP backend
schema checks passed. Final inventory found no owned qmtcli worker/server or IDA
extractor remaining; both shared clients were responsive. Work remains in_review.

## Python 3.15.2 compatibility and big-QMT preflight (2026-11-01)

Python.org lists 3.15.2 (2026-10-25) as the latest stable release:
https://www.python.org/downloads/release/python-3152/ . Existing uv 0.12.23 has no
managed download for that request. Used the official Windows x64 embeddable ZIP,
SHA256 d012f3aa29cf07436dae8aea1fec0fd195c2612a0b059b1f915ae0afb9ad1f62,
under the research python315-embed directory. Only that isolated runtime's ._pth
includes this worktree's src; no default interpreter or Windows registry change.

| Conclusion | Verification | Result and limit |
|---|---|---|
| Latest stable Python native account queries | python315-embed/python.exe verify-qmtcli-python315.py, real MiniQMT, SDK import forbidden | Python 3.15.2, 21 complete JSONL snapshots, CLI positions/orders/full snapshot, server-side cancelable filter and invalid-account recovery all pass; exit=0 |
| Returned fields | Same script using separate SDK-compatible reference process | Assets/positions/orders compare against SDK canonical fields; trade-order identities and direction/quantity checks pass; SDK reference remains Python 3.11, not a claim of SDK support on 3.15 |
| Big-QMT prerequisites | Current file hashes, process and userdata queue inventory | All five pinned module hashes match; XtItClient is absent and both userdata request queues absent; big-QMT live handshake/data are not tested |

Private receipts: recovery/five-areas/qmtcli-fully-native-python315-live.json
(source hashes bound), recovery/big-qmt/runtime-preflight-20261101.json. Both under
the existing qmt-ida research root. Latest native sample min/median/max collection
31.806/45.956/247.012ms; no cross-runtime performance claim. No production code change
was needed and no owned query worker remains. Shared MiniQMT processes responsive.

Official external xtquant API is a Python library talking to MiniQMT; QMTCLI's
native JSON interface is a separate protocol implementation using vendor queue
runtime, not an official drop-in Python package. Big-QMT additionally has its
client-managed Python/ContextInfo API. Big-QMT next validation needs the normal
logged-in client/service: profile and queue readiness -> normal real-PID handshake
-> account enumeration -> 60-byte asset reply -> independent UI/official API
comparison -> position/order/trade codecs and lifecycle checks. Existing MiniQMT
76-byte asset parsing must not be reused for big QMT. A big-QMT production adapter
has not been added or accepted by this test.

## Native market-data protocol tests (2026-11-01, research only)

Authorized by the user's request to test quotes/subscriptions/auction access.
No production QMTCLI market backend was added in this slice. A separate bounded
research client was built against observed ordinary SDK requests and server code,
then run on Python 3.15.2 with xtquant imports explicitly forbidden. It reuses the
bundled pure-Python xtbson codec, not the CPython IPythonApiClient extension.

Direct sources: miniquote handlers getFullTick 0x81540, subscribeQuote 0x8B770/
0x6C160 and unsubscribeQuote 0x8F270; net.dll NetPackageHeader::decode 0x4D640;
utils.dll exported generateCRC 0xD5200. Passive hooks were attached only to this
test's own ordinary SDK client and removed/ended with that client. No auth state,
configuration or process identity was modified. Native authPid names the actual
calling process PID; no borrowed identity, patched check or replayed authentication.

Protocol findings: 12-byte >IIHH header, zlib body, CRC flag 0x2000; CRC over the
compressed body equals zlib.crc32(body, 0xffffffff), stored big-endian. Calibrated
against vendor generateCRC for three synthetic vectors and observed bidirectional
frames. First auth request lacks the CRC trailer, normal replies/requests include
it. Request params are BSON arrays with named elements, not positional 0/1 keys.
A generic BSON decoder displays arrays as lists and hides those names. The probe
encodes through the maintained codec and changes only the params container tag.
Native notifications observed from history supply use kind=4, flags=0x2041; ordinary
request/reply uses kind=3, flags=0x2042 (initial auth request 0x42).

| Test | Actual check | Result and limit |
|---|---|---|
| Native snapshot reads | verify-native-quote-rpc.py, real localhost:58610, Python 3.15.2 | Two securities, 18 public fields and four five-level arrays match SDK control; no xtquant or BSON C extension imported |
| Numeric comparison | Canonical raw BSON vs SDK JSON values | All fields/integers exact; two floating price entries differ by 1.7763568394002505e-15; explicit float tolerance 1e-12, difference retained in receipt |
| Subscription lifecycle | Two direct subscribeQuote requests and matching owned unsubscribeQuote requests | Both return positive subscription IDs and ErrorID=0; both unsubscribed; observation yielded 0 quote push frames, so actual market event delivery is unverified |
| Auction history vs continuous control | Direct requestFromCache, two securities, 2026-10-30 09:15–09:26 and 09:30–09:32, cap 200 | Both windows return only PT/CP metadata, no records; ordinary SDK control also returns 0 rows. No auction field/quantity interpretation established |
| Historical supply | Native supplyHistoryData2 plus real asynchronous notification, same request via SDK control | RPC accepted=true; notification finished=0,total=-1,message=创建下载任务失败. The download failed; request acceptance is not data success. Exact downstream reason remains unresolved |
| Frame negative controls | check-native-quote-framing.py under Python 3.15.2 | Fragmented/coalesced frames handled; corrupted CRC, truncated/oversized frames, unknown methods and non-caller PID rejected before send where applicable |
| Resource cleanup | Owned-process inventory and shared-client response check | 0 owned probes remaining; MiniQMT/miniquote responsive; only the probe's own subscriptions removed |

Latest snapshot timestamps are 2026-10-31 13:34:26 and 11:30:00 +08:00. These are
cached quotes, not proof of fresh trading-session data. No polling result was
relabelled as a subscription callback, and no supply notification counted as a
market quote event. A bounded log search found no matching supply failure text;
it did not establish a more specific download root cause.

Private receipt root: F:/projects/_research/qmt-ida-20261031/recovery/five-areas/.
Primary results: native-quote-rpc-live.json (probe source hash),
native-quote-framing-checks.json, native-quote-protocol-profile.json and
quote-rpc-decoded-shapes.json. Negative receipts retain the initial CRC-boundary
failure, positional-parameter failure and exact BSON/JSON float comparison.
Raw socket buffers stayed in probe memory; only public market schemas/values and
protocol metadata were persisted. Current server/library hashes recorded and
compared with prior inventory when available. Formal QMTCLI native quote commands,
real subscription data, auction samples/semantics and disconnect recovery remain
unfinished. The new probe is not an SDK ABI wrapper or a production release.
