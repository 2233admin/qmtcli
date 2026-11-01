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

## Native full-tick integration slice

Authorized: combine usable native access with official SDK comparison. Extend the
existing full-tick CLI/RPC/JSONL/MCP command with explicit backend selection; keep
SDK as default, preserve its symbol mapping and timestamps, require no account.
Acceptance: actual Python 3.15.2 formal entry points with xtquant imports blocked,
two-symbol field comparison to SDK 3.11 (float serialization tolerance 1e-12),
bounded framing/CRC/decompression and negative controls, cleanup on failures.
Reuse the installed pure-Python BSON codec via isolated relative package imports;
no broker vendoring, new package, compiled Python extension or custom BSON codec.
Pin the five verified runtime binaries. Connect only to the existing loopback
service and authenticate the actual caller PID. No generic native RPC escape hatch.
Snapshot connections are owned per request: the earlier unsupported long-running
download frame must be identified before quote connection reuse is accepted.
Historical payload decoding, push delivery and auction semantics remain separate
unaccepted work; this slice must not claim full native market coverage.

## Rust direct-client experiment

User authorized trying Rust against the official get_full_tick business contract.
Keep this in experiments/native-quote-rs, not a replacement of the Python CLI.
Acceptance: compiled Rust executable/library directly authenticates its actual PID
and reads two-symbol snapshots from the pinned MiniQMT runtime, with no Python
subprocess, SDK import or broker DLL load; compare fields/integers to SDK 3.11 and
floats at 1e-12 absolute tolerance. Keep loopback, per-query socket ownership,
timeouts and read-only method allowlist. Test framing/CRC failures and cache misses.
Reuse MongoDB's maintained bson crate plus flate2, crc32fast and sha2; the latter
three and serde_json are already cached locally. bson is newly fetched through
Cargo; use its lockfile, no custom BSON codec or C compression backend. These
libraries fit the exact serialization/compression/hash boundaries and avoid
Python ABI dependencies. The noncanonical named BSON array needs only the same
small container-tag adaptation already validated in the Python implementation.
No history, subscription, account queries, trading writes or speedup claim.

## Client-behavior research: keepalive and idle reuse

User directed further development from the installed client's actual behavior.
Investigate the previously unsupported frame using own connections and pinned
static code, rather than assuming a published business API specifies transport.
Acceptance for this research slice: capture bounded header/CRC metadata, identify
the native sender, test a connection across multiple idle control frames and keep
the result distinct from an implemented Rust persistent-session API. No shared
process hooks/restarts, PID spoofing, new downloads or trading actions.

## Offline Rust session slice while counter login is unavailable

Implement the observed kind=1 keepalive branch and explicit retained QuoteSession.
Keep QuoteClient.get_full_tick as the existing one-shot convenience method. Connect
validates the pinned runtime and authenticates once; every read has a fresh wire
sequence/deadline. Any wire/data failure discards the socket; reconnect is an
explicit new connect, never automatic replay. Validate on owned loopback fixtures
with no real broker/login dependency: heartbeat CRC/flags/padding, fresh results,
single authentication, peer EOF, timeout and malformed response cleanup. Actual
retained Rust connection against Mini/Big QMT remains separate live acceptance.

## Performance comparison under unavailable live quote service

User requested measured performance. Compare Rust release, native Python 3.15 and
the installed SDK in its compatible runtime against one owned loopback replay
fixture; do not restart QMT or infer counter latency from replay numbers. Use
identical synthetic tick-shaped 2/1000-record payloads. Time retained requests,
requests plus JSON rendering and decoder components separately; process startup
is a distinct warm-filesystem/process-cold measurement. Validate output counts,
field/depth/timestamp checks and expected server request counts, recording errors.
At least five alternating blocks per case, median/range, shared-host load, client
CPU/memory and separate untimed profile. Use existing hyperfine and psutil where
appropriate; custom adapters only connect actual APIs to the common fixture.
No real SDK-vs-native QMT speedup claim while port 58610 is unavailable.

## Performance ablation

User authorized running the ablation through completion. Hold payload, runtime,
validation and process lifetime fixed; vary retained/recreated session and JSON
rendering in paired alternating blocks, then sweep 2/100/500/1000 records within
the existing public 1000-symbol limit. No weakened production checks. Rust session
recreation includes its actual runtime fingerprints, which must be distinguished
from Python socket/auth recreation. SDK retained results remain a reference; no
assumption that its reconnect method creates a fresh connection. Preserve raw
samples and verify query/auth deltas against the owned fixture.

## Official data-path review and current-stable Rust rerun

User requested the official treatment of JSON/batch costs and a current Rust run.
Read installed SDK source plus primary docs: distinguish full-tick native JSON
parsing from BSON callback delivery and buffered historical data. Verify the latest
stable via official release and rustup; install a pinned side-by-side toolchain,
leaving defaults intact. Compare unchanged Rust source/lockfile under 1.99.0 and
1.99.1 in the same five interleaved replay rounds, retained snapshots, JSON and
decoder components, plus native Python/SDK references. Preserve original receipts;
do not attribute noise or a compiler bump to a production architecture change.

## Approved two-core Rust workspace, 2026-11-02

User confirmed two Rust cores in one Cargo workspace with one QMTCLI entry.
qmt-quote and qmt-trade must not depend on one another. First implement the
workspace, move the tested quote source without semantic changes, and deliver
CLI/rpc/JSONL quote access with retained sessions and truthful discovery. Port
account codecs into qmt-trade; account transport is unavailable until its isolated
worker/ABI migration is accepted. Python production stays unchanged. Existing
experiment main/benchmark become adapters to the single quote implementation;
remove their legacy wire source now and keep adapters only while local research
drivers use them. A future adapter removal requires updating those named callers.
Protect old quote behavior with existing tests; new entry/codec behavior follows
red/green tests, owned replay validation, and the existing structural gate.
No new registry dependency: clap was checked but is not locally present; this
slice has only fixed entry modes plus JSON requests, so std args suffice without
implementing a general option parser. Use Cargo's maintained workspace/lockfile
mechanism rather than a custom build orchestrator.

## Complete Rust account query path, 2026-11-02

User authorized filling the remaining SDK-architecture gaps. Port the verified
read-only account protocol, correlated/fragmented list replies and sequential
four-section snapshots. Implement version-pinned vendor DLL calls only inside
the same executable's private worker; parent owns deadlines, worker generation,
reply queue reservation and a kill-on-close Windows job. Add account commands
to the shared CLI only when the transport implementation passes its checks.
Use Microsoft's maintained windows-sys bindings for mapping/loading/jobs/random,
not handwritten Win32 declarations; pinned 0.61.2 with only needed features.
The private vendor C++ ABI necessarily follows the already verified Python
adapter. Test pure queue fixtures, bad source/seq/action/fragment/empty cases,
worker timeout/crash and owned DLL queue probes before any real-service claim.
Native unsolicited event semantics, subscriptions and real account acceptance
remain distinct; do not fabricate events from repeated snapshots or call query
responses a complete SDK replacement. Existing read-only boundaries persist.
# Approved slice: Big QMT public reads (2026-11-02)

Deliver the installed FormulaLib/qmt_api public read path in qmt-quote and Rust
QMTCLI, with explicit `backend:formula`: instrument-detail (one symbol),
daily-bars (latest 1..1000 daily OHLCV/amount bars), full-tick (one cached snapshot).
Follow the installed vendor's named-document BSON protocol, not MiniQMT auth/wire.
No arbitrary methods, strategy execution, account queries or subscriptions in this
slice. Pin FormulaLib/net fingerprints, resolve the installed formula config port,
connect only to loopback, retain one owned session, bound frames and deadlines,
invalidate failed sessions without replay, and label cache source and timestamps.
Acceptance: offline protocol/normalization/CLI tests, current Big QMT all three
commands through the packaged standalone Rust exe, discovery/schema and cleanup.

## MiniQMT first (2026-11-02)

User priority: finish the read-only MiniQMT Rust backend before extending Big QMT.
First close the actual four-section account and retained quote-session acceptance;
then native history/market subscriptions/auction semantics and account events with
recovery consistency. Keep qmt-quote/qmt-trade independent and QMTCLI agent-facing.
Order placement/cancellation/transfers remain outside this repository's contract.
Use `experiments/accept_miniqmt.py` for sanitized real-entry acceptance: explicit
actual/synthetic scope, same-account snapshots, rejected input preserving session,
two-stock snapshots across optional idle, independent sessions and owned-worker EOF.
This tool does not prove subscriptions, forced broker reconnection or SDK parity.
Current real-entry preflight: MiniQMT queue missing and 58610 connection timed out;
only the Big QMT host is running. Actual acceptance requires normal MiniQMT login.
