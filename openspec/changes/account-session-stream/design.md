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

## Sunday availability and corrected auction sampling (2026-11-01)

[K] Host Get-Date: 2026-11-01 Sunday, China Standard Time (+08:00). New evidence
supersedes the broad inference that no historical auction samples are available:
the earlier empty result was specific to 2026-10-30, while this installation has
older data. No downloads were performed in this follow-up.

| Dataset | Current actual result | Path and limitation |
|---|---|---|
| Instrument metadata | Nonempty; SDK filtered view 36 fields, native response 55 fields | Native Python 3.15.2, no xtquant import; full raw field semantics not newly certified |
| Instrument type | Stock classification returned | SDK control |
| Sectors / members | 854 sectors; existing 沪深A股 sector returns 5224 codes | Both native and SDK; current client's cached inventory, not a claim of latest official universe size |
| Trading dates | 2026-10-26 through 2026-10-30, five dates | Native and SDK, requested 10-26 through 11-06/07; not future calendar completeness |
| Dividend factors / financial data | Nonempty cached dividend factors; cached balance-sheet/income tables | SDK raw client reads, no pandas conversion or dependency installation |
| Historical 1d / 1m / tick | Two securities each return five requested records | SDK control; K-line returns dict-of-columns, so dict length must not be counted as row count |
| Cached auction window | 2026-10-19 09:15–09:26: 600000.SH 182 rows, 000001.SZ 60 rows | SDK decoded tick arrays; native requestFromCache also returns actual B payloads of 1614/1012 bytes plus T/HIS/DV/DT/PT/CP metadata |
| Cached continuous control | 2026-10-19 09:30–09:32: both securities 41 rows | SDK control; these data do not validate live push |
| Missing datasets in current request | 000300.SH weight map and holiday list empty | Empty cache/request result; no claim these datasets require an open market |

Cache coverage observed from limited trailing samples: day bars 2026-10-14 through
10-20, minute bars 10-20 13:09–13:13, tick samples 10-19 15:25–15:30. These are older
cached records. SDK history-supply failure on the requested 10-30 range remains
real; Sunday alone does not explain task creation failure, and should not be used
as its diagnosis. Live quote push still needs actual new data; historical auction
semantics can be validated against stored trading-day data without waiting for open.

Native historical compressed B decoding is not implemented/validated in the probe;
receipt proves the payload was received, not that all native fields have been
restored. No meanings for auction matched/unmatched quantities have been assigned.
Private receipts: nontrading-data-availability.json and
native-nontrading-data-availability.json under existing recovery/five-areas root.
Scripts probe-nontrading-data.py and probe-native-nontrading-data.py ran with exit=0.
All native queries used the real caller PID and allowed read methods only.

## Applied QMT cache maintenance (2026-11-01)

User requested data maintenance. Scope selected after the two-stock pilot: refresh
only existing SH/SZ/BJ daily files, plus the pilot stocks' needed minute/tick windows.
No new whole-market minute/tick download, QMT install, client restart, configuration
change, trading/account operation or synthetic bar fill was performed. This is an
actual cache update, not only a request/diagnostic test. No recurring task installed.

### Backup and delivery

- Original pilot six files were copied and SHA256-checked before writes:
  F:/projects/_research/qmt-ida-20261031/cache-maintenance-backups/20261031T231627Z/.
- Complete existing daily inventory: 5579 files, 121348888 bytes, archived with
  stdlib ZipFile into existing-daily-20261031T232658Z/daily-cache.zip under the same
  backup root. Every source buffer was hashed into manifest.json; archive entry
  count and full ZIP CRC test passed. Final archive SHA256:
  f2ce844c89c8597e617fdffc2e550aec850b996b139fa25a060933da25acc990.
  Full daily archive was taken after the two-stock pilot; its originals remain in
  the pilot backup above. Both are retained for rollback provenance.
- First per-file bulk backup was slow and stopped before any download stage.
  Its 988 duplicate copies in the precisely verified owned partial directory
  existing-daily-20261031T232424Z were removed after full archive validation;
  original QMT files and complete backups were retained.

### Verified results

| Scope | Actual check | Result and remaining limits |
|---|---|---|
| Existing daily caches | Fresh SDK process, all 5579 codes, actual time/close/volume rows in October query window | 5571 have 2026-10-30 data; 5566 cover every expected session from 10-21 to 10-30; 0 nonfinite/negative checked values and 0 duplicate/unordered timestamps |
| Daily exceptions | Actual dates plus cached contract metadata | 13 codes with missing session dates or no October rows; includes 6 older latest dates and 2 with no records in query window. Metadata review produced no pre-listing explanation. Do not call empty October queries physically empty files, or infer all gaps are corruption/suspension |
| Normal metadata control | 600000.SH against exception IsTrading flags | Normal control also returns IsTrading=false on Sunday; this flag alone does not explain exceptions. Raw InstrumentStatus/expiry fields were retained without inventing a status mapping |
| Pilot daily/minute coverage | verify-qmt-cache-coverage.py, fresh process | Both 600000.SH and 000001.SZ have all 8 expected daily records and 1928 minute records (241/session), timestamps ordered/unique, finite prices/amount/volume fields |
| Pilot auction tick maintenance | Official single-symbol supply_history_data, new physical 20261030.dat files, independent historical readback | 10-30 09:15–09:26 returns 190 rows for 600000.SH and 64 for 000001.SZ. Original 20261019 tick files retained. Tick request covered 09:15–09:32, not the whole trading day |
| Cleanup | Final process inventory and shared-client response | No owned maintenance or IDA extraction processes remain; shared MiniQMT/miniquote responsive; main working tree user's four pre-existing changes preserved |

### Download behavior learned

- Two-stock day download passed; initial immediate minute readback still saw old
  values, while later independent process saw new files/data. A completion callback
  and fresh cache visibility must be checked separately; precise SDK writer ordering
  was not established.
- Batch supply_history_data2 was unreliable in this run: second same-client batch
  had no progress, fresh-client retry passed, and a later fresh batch stalled at
  118/200. Such batches were stopped and kept as failed/incomplete receipts.
- Documented single-symbol client.supply_history_data was tested on 20 missing
  codes; 18 returned actual target-date data while 2 stayed older. It was then used
  for the remaining 3663 codes; all calls returned without exceptions. This is not
  the acceptance criterion: the independent data-read results above are authoritative.
- The same single-symbol entry point actually generated new tick data although
  supply_history_data2 reported 创建下载任务失败 or no progress. The batch route's
  exact internal defect remains unresolved; no authentication check was altered.
- An experimental native-maintenance probe hit an unsupported RPC frame while
  waiting for successful download notifications. It was not used for bulk data
  maintenance, and native full-history decoding is not declared complete. Actual
  maintenance used the installed supported SDK in its compatible research runtime.

Private durable receipts under existing recovery/five-areas: cache-maintenance-summary.json,
existing-daily-maintenance.json, existing-daily-maintenance-resume.json,
legacy-daily-maintenance.json, existing-daily-maintenance-verification.json,
cache-maintenance-coverage.json, cache-maintenance-exceptions.json/.csv and
cache-maintenance-tick-legacy-600000_SH.json / -000001_SZ.json. The auction receipt
now records the still-failing batch download separately from successful cached
readback after the legacy download. Old negative receipts are retained separately.
An initial full-check script list-vs-array comparison error was corrected before
final verification; it was not classified as a market-data failure.

Reusable research tools: maintain-qmt-market-cache.py, maintain-existing-qmt-daily.py,
maintain-legacy-daily.py, verify-qmt-cache-coverage.py and review-qmt-cache-exceptions.py.
The scripts adapt existing normal SDK calls and stdlib archival; no new package was
installed. This turn changed data and receipts/docs only, not QMTCLI production
Python code, so its unchanged unit suite was not rerun as a substitute for data QA.
Review items remain the 13 per-symbol gaps and batch/native maintenance lifecycle;
no fabricated records or blanket completed-software claim.

## Formal native full-tick integration — 2026-11-01

`full-tick --backend native` now uses a dedicated read-only quote adapter, also
reachable through full_tick RPC/JSONL and the generated qmt_full_tick MCP tool.
SDK stays the default and no automatic fallback is performed. The public symbol
mapping/timestamps are preserved; account/session state is not required or reused.
Only authPid (actual process PID) and getFullTick are allowlisted. Existing local
miniquote receives outbound loopback TCP connections; no listening server is added.

The five research-verified binary fingerprints are pinned in native_quote.py.
Installed xtbson.bson37 is reused under a private package namespace, with _cbson
blocked, relative imports and no sys.path edits. This wheel avoids implementing
another BSON codec or adding dependencies. Custom code owns framing >IIHH,
named BSON array container adaptation, bounded zlib decoding, the verified CRC32
variant, request sequences, shared connect/auth/query timeout and socket cleanup.
An unknown frame, truncated reply, CRC mismatch, unsupported runtime or service
error explicitly fails the request. Empty result mappings remain valid cache misses.

The research download probe's unknown long-running frame is still unresolved.
Consequently each snapshot owns its socket and closes it on success/failure;
JSONL process reuse is supported, native quote connection reuse is not claimed.
No historical B payload decoder, quote push implementation or auction semantics
was smuggled into snapshot acceptance. Big QMT remains untested.

| Conclusion | Check / receipt | Result and limits |
|---|---|---|
| Formal native snapshot works on Python 3.15.2 | Private verify-formal-native-quote.py; recovery/five-areas/formal-native-quote-acceptance.json | Actual CLI, RPC and JSONL; xtquant imports forbidden and BSON _USE_C false checked in each native process. |
| Snapshot matches official SDK | Python 3.11 installed SDK get_full_tick versus formal native CLI/RPC/JSONL | Two stocks, 18 fields each, all four depth arrays length five. Three floats differ by 1.7763568394002505e-15; explicit tolerance 1e-12, other fields/integers exact. Cached timestamps preserved, not a live market test. |
| JSONL errors do not stop subsequent reads | Ten valid snapshot requests with invalid timeout inserted after five, then EOF | Ten successes, invalid id echoed as failure, later requests succeed, clean process exit; snapshot sockets are not retained. |
| Protocol/public failure behavior has offline coverage | tests/test_native_quote.py and tests/test_mcp_server.py; uv run --no-sync --extra dev pytest -q | Fragments/coalescing, CRC, sizes, decompression bomb, unknown kind, sequence mismatch, invalid inputs/results, auth rejection, empty cache, deadlines, runtime fingerprint and pure codec isolation. Final frozen tree: 427 passed in 5.98s, exit 0. |
| Static/structural gates pass | ruff check .; ruff check src/qmtcli/native_quote.py --select C901; git diff --check; code-intel . --mode normal | All exit 0. Code Intel Outcome completed; run evidence C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/1793517799350-91644-core/run-complete.json. Only this documentation receipt changed after the frozen scan. |

Warm filesystem/process observations in the acceptance receipt: separate CLI
process 222.491 ms, JSONL process serving 10 snapshots plus one validation error
319.632 ms. An earlier cold CLI launch took 8645.765 ms under concurrent host load.
These are samples including process startup/profile checks, not an SDK speedup
benchmark or native connection reuse measurement. No average/p95 claim is made.

Closeout: use this existing OpenSpec as the local in_review state, no new external
tracker entry or duplicate KB state. The reusable interface is documented in
docs/native-quote.md; research acceptance script/receipt remain private outside
the repository. No vendor code, credentials, trade writes or package installs.
Main checkout's pre-existing dirty files are preserved. No remote push/merge.

## Rust direct full-tick experiment — 2026-11-01

Question answered: a compiled Rust library/executable can request MiniQMT directly
using the official get_full_tick business shape, with no Python child process or
broker DLL loads. Isolated implementation: experiments/native-quote-rs, publish=false,
locked dependencies, not wired into the formal Python CLI backend. Rust 1.99.0 /
Cargo 1.99.0, Windows x64 GNU toolchain. Each request validates the same five pinned
runtime files by reading SHA256 only, uses its own real PID and loopback socket,
then releases that socket through Drop on either success or error. No trade writes.

The library accepts explicit security codes and official market selectors SH/SZ.
It returns bson::Document with original numeric types; CLI exports a JSON envelope.
Maintained wheels: MongoDB bson 3.1.0 with serde/serde_json-1, flate2 1.1.10,
crc32fast 1.5.2 (existing cached version), serde_json 1.0.154, sha2 0.11.1.
Cargo.lock pins transitive dependencies. Custom code only adapts the known local
framing, named BSON params array, PID auth, deadlines and response identity.

The official market control contained 51,196 records (~20 MB JSON), so the prototype
uses bounded streaming decompression, 16 MiB frames / 64 MiB decoded payload, with
16 KiB output chunks. These bounds are local experiment limits, not official API
limits. An initial real market request failed because FlushDecompress::Finish on
the first call assumes the whole output fits. The primary flate2 source documented
that constraint; changed to None for streaming, and added a >64 KiB positive
regression alongside overflow/truncation/trailer controls. This failure is retained
in rust-native-quote-deflate-negative.json, not recast as an environment failure.

| Conclusion | Verification / primary receipt | Result and limits |
|---|---|---|
| Rust directly retrieves real quotes | verify-rust-native-quote.py with PATH restricted to Windows System32; executable PE imports inspected | Ten two-stock reads succeeded, both 18 fields and five-level arrays; explicit invalid-input/runtime failures and userdata_mini recovery also passed before the market comparison. Imports are seven Windows system DLLs, no Python/xtquant DLL. Rust source has no process spawning or DLL loading. |
| Initial two-stock SDK acceptance passed | rust-native-quote-acceptance.json and retained market-absolute-negative receipt | Fields/integers/arrays match SDK 3.11; three float differences per snapshot are 1.7763568394002505e-15, within the original absolute 1e-12 criterion. |
| Whole-market read works but strict SDK JSON float check fails | diagnose-rust-market-differences.py; rust-market-differences.json | SDK and Rust both 51,196 records, same keys/fields/array lengths/integers. 14,086 float values differ, all exactly one ULP; six exceed absolute 1e-12 (index values ~11,000–13,000). This extra criterion remains FAILED; no tolerance was silently widened. Main acceptance script retains passed=false for that extra check. |
| Rust preserves raw market values exactly | verify-rust-vendor-bson.py; rust-vendor-bson-control.json | 51,196 records, zero value differences versus the installed independent pure-Python vendor BSON decoder; no float tolerance. Both controls use actual caller PID. Research-only Python response limit increased in that process to 64 MiB; no production Python code changed. xtquant not imported, vendor _USE_C false. This localizes the observed discrepancy to the SDK JSON path versus raw BSON; the exact vendor JSON conversion function was not traced. |
| Final source gates pass | cargo test --locked: 10 passed; cargo clippy --locked --all-targets -- -D warnings; cargo fmt -- --check; pytest -q: 427 passed; ruff check .; git diff --check | Exit 0 for these checks, full command paths use experiments/native-quote-rs/Cargo.toml and the shared no-sync Python dev environment. Raw check stdout is in this turn's tool transcript. No latency/speedup acceptance claim. |
| Structural check completes | code-intel . --mode normal | PASS / completed; C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/1793523199005-83856-core/run-complete.json. Only documentation receipts changed after the source scan. |

Private receipts live under F:/projects/_research/qmt-ida-20261031/recovery/five-areas.
Final executable SHA256 378ad9111d56d2ae5349aa947c537f36870322a3781b0dc5f4d92a142133eb56;
Cargo.lock SHA256 adea45f7f25f68e7a9f4f9e2f06d776d3c06d82611d8777cd2ae95f52f1b0b57.
Debug-process samples: two-stock 155.582–204.320 ms; market 5660.247 ms in the exact
BSON control. Startup/hash checks/JSON export included; no SDK speedup inference.

The experiment answers the user's Rust feasibility question. It does not establish
bitwise SDK JSON compatibility across every instrument, subscription/idle handling,
history, auctions, account native IPC or Big QMT. Keep the overall change in_review.
No new external tracker, duplicate KB state, remote push or merge. Durable contract,
limits, wheels and failure evidence stay in this OpenSpec and the experiment README.
No shared process was restarted or stopped; generated targets remain ignored and
are retained so the user can run the verified executable. Main's dirty files remain.

## Behavior-first transport research: actual keepalive — 2026-11-01

User directed research against the software itself. This slice used own native
socket connections and existing pefile/Capstone for bounded static inspection;
no official endpoint assumptions, SDK calls, shared-process hooks/restarts, data
downloads or trading writes. Production Python/Rust code was not modified.

| Conclusion | Evidence | Result / limit |
|---|---|---|
| A real control frame previously rejected by strict readers is kind=1 | probe-native-quote-idle.py; native-quote-idle-observation.json and -65s.json | Authenticated real caller PID, ten same-socket two-stock reads, then passive idle. Two control frames over 25s, nine over 65s; kind=1, observed flags=0x2e40, sizes 16–19, all CRCs valid. |
| Native sender identifies these as keepalive | inspect-net-header.py; net-header-static.json against pinned net.dll | Export doSendKeepAlive RVA 0x447E0 passes kind=1 at 0x448C0 to NetPackageHeader constructor 0x4D4F0. Constructor stores dx into kind at +0x10 (0x4D51B). Sender then calls encode 0x4D870 at 0x4492D. Earlier kind=12 heartbeat hypothesis is rejected; its decoder branch is not evidence of heartbeat type. |
| Sequence bits share the flags word | Header constructor/decode static instructions | Constructor takes seq>>32 and stores its upper nibble with feature flags; decode reconstructs high sequence bits. Observed 0x2e40 must not be hardcoded as the only keepalive flag value. Sender masks sequence to 36 bits at 0x448A9/0x448B3. Normalizing the four sequence bits yields 0x2040 for this observation. |
| Socket can survive idle without invented ACK | Both live probes | Same socket: 10 queries, 25s or 65s passive reading, query 11 succeeds; one auth, no control packets sent by probe. Server timing varies, so these samples do not establish a fixed heartbeat interval, infinite connection lifetime or disconnect recovery. |
| Original unsupported download frame is not conclusively identified | Original maintenance probe retained no failing header | Kind=1 appears around 4s and would fail that old whitelist, consistent with the old failure timing; this is an inference, not proof that the exact old frame was identical. The new control frame itself is directly observed and statically identified. |

Private evidence is under recovery/five-areas in the existing research root.
The probe records headers, CRC booleans and body hashes only, not arbitrary payloads.
Owned sockets close in finally; both shared MiniQMT processes remain untouched.

This removes a concrete uncertainty for Rust connection reuse. It does not claim
Rust reuse is implemented: current wire::read_reply requires a matching kind=3 RPC
reply and will reject an interleaved kind=1 control frame. Next implementation
must validate control framing/CRC before routing it separately from request
sequences; subscription kind=4 notifications remain a distinct, unaccepted path.
Keep the existing strict failures for unknown/corrupt frames and add regression
fixtures before accepting a retained Rust socket. No broad SDK/software completion.

Only research scripts/private receipts and these OpenSpec notes changed in this
slice; unchanged production Rust/Python suites were not rerun as a substitute for
the actual idle experiment. Overall state remains in_review, no new tracker/KB
copy, remote push or merge. Local docs commit preserves the verified finding.

## User-opened full QMT: actual external-service gate — 2026-11-01

User opened full QMT and authorized read-only testing. Current PID 15856 is
XtItClient.exe at the installed bin.x64 path, independently verified using Windows
QueryFullProcessImageName with PROCESS_QUERY_LIMITED_INFORMATION. Process has a
responsive window. Regular module enumeration fails for this process: loaded
state is UNKNOWN, not false. Earlier automatic loaded=false observations from an
empty module collection are superseded. No process privileges were changed.

| Conclusion | Actual evidence | Result and limit |
|---|---|---|
| Full client is open | Limited image query, process metadata and Orca list-windows | Installed XtItClient identified, not MiniQMT. UI title/account identifiers are excluded from durable receipts. Bundled node/sky kernel fails sandbox initialization; installed Orca provider can identify window, but its screenshots remain occluded even after restore. No UI clicks or authentication actions performed. |
| Existing Rust Mini quote route is unavailable in this full-client-only state | Actual qmt-native-quote-experiment.exe root + two symbols | Exit 1, ok=false, Windows error 10061. No service at the previously verified Mini quote port 58610. Current full-client process listens on 58600; that endpoint is not assumed to be quote RPC and was not sent guessed messages. |
| Expected Big native queues do not exist | Path checks distinguish ObjectNotFound from denied inspection | userdata/up_queue_xtquant, up_queue_win_xtquant and winsemaphore_flag_xtquant absent. No fake queue created and no account query sent. |
| Latest startup logs deny external API service | probe-big-qmt-live.py; private recovery/big-qmt/live-probe-20261101.json | Capability log at 17:37:06 has mdl_auth_xtquant=0; at 17:37:08 logs exactly "The XtQuantServer is not allowed to start." Current process began 17:36:53. Static loadFromConfig 0xCD8F0 calls checkModule(mdl_auth/mdl_auth_xtquant); false branch emits that exact message, true branch calls startQuantServer 0xE5290. No capability/authentication/configuration modification. |

This is a real negative connectivity result, not a missing-login assumption or
proof of a Rust decoding/Python-version defect. The module gate concerns this
external service; it does not establish that every internal client data interface
is unavailable. Static candidate export surface (Formula runStrategy 0x1632A0,
initPythonList 0xEC930) is recorded privately, but running an existing strategy
could have trading side effects, so no such function was invoked. Legitimate
internal read-only access still requires separate investigation/acceptance.

Private scripts/receipts: probe-big-qmt-live.py, inspect-big-strategy-surface.py,
live-probe-20261101.json, internal-strategy-export-surface.json and updated
recovery/big-qmt/README.md. Only capability booleans and exact service-denial
messages are persisted, not raw authorization/account logs. Production source
is unchanged; no unit-suite rerun substituted for the real failed connection.
User's running full client is left open, no server checks were bypassed. Overall
state remains in_review, Big account/query completion unchecked, no remote push.

### Login-state reassessment after user weekend hypothesis

Local date/time check confirms Sunday 2026-11-01. Sanitized current-session log
classification (check-big-qmt-login-state.py, private login-state-check-20261101.json)
finds repeated login-failure phrases through 19:28, alongside some success markers
whose client/market/trading-account component attribution is not established.
No explicit weekend/maintenance/out-of-service-time phrase was found in this
bounded scan, so weekend maintenance remains a hypothesis, not a verified cause.
The failed-login markers are new context; they do not prove that failed login
caused the startup capability value zero, nor that the value is a permanent
entitlement restriction. Preserve the directly observed gate/refusal results but
recheck after a confirmed relevant counter login before final capability judgment.

## Login-independent Rust session implementation — 2026-11-01

User asked what can proceed while login is unavailable. Implemented the next
bounded slice in experiments/native-quote-rs: QuoteClient::connect returns an
owned QuoteSession, authenticating once after pinned-runtime validation. Each
get_full_tick sends a fresh sequence and has its own deadline. The existing
QuoteClient::get_full_tick remains the one-shot convenience API. Session ownership
is single mutable Rust ownership; no background network listener or new dependency.

The frame reader now routes directly observed kind=1 keepalives separately from
kind=3 RPC replies. It normalizes only flags bits 11:8 (high sequence bits), accepts
the pinned 0x2040 control feature pattern and size 16–20, verifies CRC and zero
padding, then continues toward the matching RPC sequence. Unknown/corrupt frames
still fail. Heartbeats do not reset the request's DeadlineStream budget. Quote
results are not cached and real server timestamps remain unchanged.

Wire, timeout or result-validation errors discard the owned socket. Later calls
fail closed; reconnect requires an explicit new client.connect, with fresh auth
and sequence. No automatic replay/fallback. Input validation errors preserve a
healthy socket; sequence exhaustion closes it instead of wrapping. Drop also
closes a successful retained connection.

| Conclusion | Actual check | Result / limit |
|---|---|---|
| Session behavior is guarded offline | cargo test --locked --manifest-path experiments/native-quote-rs/Cargo.toml -j 4 | 18 passed, 0 failed; fixture execution 0.26s. New tests were added first, expected E0425/E0433 missing QuoteSession errors observed, then implementation added. |
| One auth, fresh reads, control routing and recovery work against fixtures | src/session_tests.rs and wire tests | Owned ephemeral loopback peers assert actual caller PID, auth once, sequences 2/3/4, distinct reply values, fragmented/coalesced keepalives, timeout cleanup, peer EOF, malformed result, auth rejection, exhaustion and explicit reconnect with sequence reset. All peer threads joined; no actual broker contacted. |
| All observed control sequence-bit variants remain distinct from RPC replies | keepalives_with_high_sequence_bits_are_not_rpc_replies | All 16 high-nibble variants accepted; corrupted CRC, unknown flags, oversized or nonzero-padding control packets rejected. Subscription notifications still unsupported. |
| CLI/library build and static checks pass | cargo build --locked; cargo clippy --locked --all-targets -- -D warnings; cargo fmt -- --check | All exit 0; final executable rebuilt. Manifest path is experiments/native-quote-rs/Cargo.toml; no dependency/lockfile changes. |
| Existing Python CLI remains intact | UV_PROJECT_ENVIRONMENT=F:/projects/qmtcli/.venv; uv run --no-sync --extra dev pytest -q; ruff check . | 427 passed in 338.93s; lint exit 0; git diff --check exit 0. Raw command output is retained in this turn's tool transcript, not an invented log file. |
| Structural gate completes | code-intel . --mode normal on frozen source | PASS / completed; C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/1793535574544-34580-core/run-complete.json. Only documentation receipts changed afterward. |

Scope remains an experimental Rust library/CLI, not a replacement of the formal
QMTCLI Python backend. Actual retained Rust session acceptance against QMT, Big
account access, real disconnect/idle behavior, historical decoding and live push
remain unchecked. No running QMT process, login flow, capability or cache was
modified. Temporary peers were test-only; generated targets stay ignored and are
retained as runnable artifacts. Main checkout's unrelated dirty files remain.
Keep OpenSpec in_review; no tracker/KB duplication, remote push or merge.

## Performance replay receipt, 2026-11-01

User requested a performance comparison while the real quote endpoint is absent.
See [the measured report](../../../docs/quote-performance.md) for final medians,
ranges, boundaries, correctness and local raw artifacts. No production backend
change: only a Rust benchmark example and this research receipt. The primary
1000-record query-plus-JSON medians are 14.93 / 18.95 / 30.18 ms for Rust release /
native Python 3.15.2 / installed SDK on Python 3.11.16. Five alternating blocks;
small requests have overlapping variation. These are owned loopback synthetic
replay results, not QMT/counter latency or a production adoption decision.

Closeout: retain existing OpenSpec in_review; no new tracker or duplicate KB truth.
Local benchmark artifacts include the initial close-classification failure and
the profiler-import baseline, distinct from the final run. All owned benchmark
workers exited normally. No global instruction changes or shared process cleanup.

Verification: `cargo test --locked --all-targets -j 4` passed 18 library tests
and 7 reused wire tests in the benchmark example; Clippy all-targets with warnings
denied and cargo fmt check passed. Shared-venv `ruff check .` passed. The prior
427-test Python result remains the baseline; Python production code did not change
and that suite was not rerun for this benchmark-only example/docs slice.
Code Intel normal completed PASS on frozen source:
`C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/1793538852150-96940-core/run-complete.json`.
Only this documentation receipt was adjusted afterward. `git diff --check` passes.

## Connection/JSON/batch ablation receipt, 2026-11-01

User authorized completing the ablation directly. See
[ablation report](../../../docs/quote-ablation.md) for five alternating blocks per
condition, ranges, paired JSON deltas, the fixed 1000-symbol limit and the exact
recreation boundary. Rust recreation deliberately includes actual fingerprint
checks; Python recreates socket/auth with its already loaded codec. No production
validation or ownership behavior was weakened. Validation/copy-cost isolation is
still pending; it is not an accepted optimization or part of this three-factor run.

Owned synthetic replay: 160 timed blocks, 12,250 timed queries plus 320 warmups,
483 authenticated connections and zero request errors. All clients and fixtures
exited normally. Independent untimed profiles and three malformed-frame negative
controls passed. One untimed SDK readiness timeout is preserved separately; no
unsupported root cause was assigned. Local artifacts and adapter/binary hashes:
`F:/projects/_research/qmt-ida-20261031/recovery/ablation/final.json`.

Verification: Rust all-target tests passed (18 library plus 7 reused example wire
tests), Clippy warnings denied, fmt, shared-venv ruff and diff whitespace checks
passed. Production Python is unchanged; its previous 427-test suite result is not
claimed as a rerun. Code Intel normal on frozen source completed PASS:
`C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/1793539904788-4416-core/run-complete.json`.
Only documentation receipts/count arithmetic were adjusted afterward. Retain
OpenSpec in_review and the real-QMT acceptance gaps; no tracker or KB truth copy,
remote push or merge. The nonresponsive task-owned rg process was identified by
PID/parent/SDK-source command and terminated; no shared process was stopped.

## Official path review / Rust 1.99.1 receipt, 2026-11-01

See [official-path and current-stable report](../../../docs/quote-rust1991.md).
Installed SDK full-tick parses native JSON; byte subscription callbacks decode
BSON; a historical K-line path uses np.frombuffer before DataFrame construction.
Primary official docs distinguish whole-quote subscriptions and bounded cached
history reads. These do not establish a universal best 500-record batch.

rustup and the official release page confirmed stable 1.99.1. Installed the pinned
GNU toolchain plus its Clippy/rustfmt side-by-side, leaving default 1.99.0 intact.
Same source/lockfile release compiler A/B plus native Python and SDK references:
200 timed blocks, 17,920 network queries (17,600 timed + 320 warmup), 4400 timed
decoder-only operations, zero request errors. All owned processes exited normally.
1000-record JSON medians old/new Rust: 12.838 / 13.620 ms, overlapping ranges and
no consistent upgrade gain across batch sizes. Do not infer a regression or
production service speedup. No return validation/copy changes were made.

Actual checks: cargo +1.99.1 release all-target tests passed (18 library, 7 reused
example wire tests), Clippy release all-targets warnings denied and fmt check
passed. Source and lockfile were unchanged; no repeated structural scan or Python
suite is claimed. Diff whitespace check passed. Preserve local raw data, versions,
SDK source extracts and hashes in `F:/projects/_research/qmt-ida-20261031/recovery/rust1991/`.
Only report/OpenSpec files changed in this slice; no tracker/KB duplicate truth,
remote push or merge. Keep overall change in_review and live acceptance unchecked.

## Rust product architecture review, 2026-11-01

User requested architecture review before delivering a usable Rust QMTCLI.
See [the review and candidate](rust-architecture-review.md): existing Rust main
is one-shot quote-only; native accounts still depend on a pinned vendor C++ DLL
in an isolated worker. Recommended candidate is a Rust parent plus the same exe
as a private account worker, sharing Dispatcher/Runtime across public adapters.
Current Python MCP does not pass the retained AccountSession; avoid copying that
lifetime difference into the new product. Preserve explicit native request subset,
envelopes/ids, non-atomic snapshots and fail-closed version boundaries.

This is a self-review/design candidate, not approval of new APIs/dependencies or
an implemented Rust account backend. Worker FFI, real retained quote sessions,
packaging and MCP scope remain explicit decision/verification points. No code,
config, QMT instance or deployment was modified. Code Intel completed PASS on
current source: `1793541903515-79844-core/run-complete.json`. Only documentation
changed afterward; no new unit/live/performance result is claimed.
