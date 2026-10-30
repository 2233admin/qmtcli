# Native MiniQMT account assets (experimental)

`asset --backend native` queries a logged-in local MiniQMT without importing
`xtquant`, `xtpythonclient.pyd` or `IPythonApiClient.pyd`. Verified on Windows x64
with Python 3.14.7. It still uses the installed client's `ringbuffer.dll` runtime;
this is a pinned C++ ABI adapter, not a vendor-independent SDK replacement.

## Use

```powershell
uv run qmtcli --path D:\DFZQxtqmt_client_real_win64 --account YOUR_ACCOUNT asset --backend native
```

Global `--path` and `--account` precede the subcommand. `--backend` and `--timeout`
follow `asset`. `--path` accepts the install root or `userdata_mini`. Without an
explicit path, existing QMTCLI installation discovery is used. The account must
be explicit; this backend never selects an account from local CSV filenames.

For RPC, JSONL `server`, or MCP `qmt_asset`, send:

```json
{"id":"asset-1","command":"asset","backend":"native","path":"D:\\DFZQxtqmt_client_real_win64\\userdata_mini","account":"123456","timeout":5}
```

`123456` is fictional. See `examples/native_asset.json`. MCP arguments omit `id`
and `command`. Available options are discoverable through capabilities/schema.

The returned asset retains the SDK's public names:

```json
{"account_type":2,"account_id":"123456","cash":1250.25,"frozen_cash":50.0,"market_value":5000.0,"total_asset":6300.25}
```

These example amounts are fictional. Values are returned from MiniQMT, not
recomputed or read from persisted CSVs. CLI keeps its existing direct-data success
shape; RPC/JSONL/MCP keep `{ok,data|error}` and request-ID behavior. Default `asset`
still uses the SDK. `status`/`doctor` continue to diagnose the SDK and are not native
readiness checks.

## Scope and failures

- Only `STOCK` asset queries, with ASCII account identifiers up to 23 bytes.
- Native response timeout: 0.1–60 seconds; child-process hard timeout adds three
  seconds for startup. Missing account/path, unsupported build, invalid response,
  account mismatch, native fault and timeout fail explicitly without fallback.
- Only native connect (10001) and asset query (20005) can be encoded. There is no
  arbitrary IPC-call interface and no order/cancel/transfer operation.
- Market-data `xtdc` tokens are unnecessary for native assets. In RPC/JSONL/MCP,
  token initialization is deferred until a non-native request needs the normal
  SDK route, so native-only sessions work without the SDK.
- Each query reserves a reply queue with exclusive creation and a random ownership
  marker. The bounded worker verifies that marker before initializing the queue.
  The parent attempts to remove only that session's reply file after worker exit.
  MiniQMT can retain a writer mapping temporarily, preventing immediate deletion.
  This first slice does not provide persistent sessions or high-frequency polling.
- It targets MiniQMT only; it does not establish big-QMT compatibility.

## Supported binary profile

Both installed files are checked before any native call. Client upgrades fail
closed until the changed ABI is inspected and verified.

| File under `bin.x64` | SHA256 |
|---|---|
| ringbuffer.dll | b40def1af839286baaf6b8bdcde7c88a0c555dbfb56d9bb3592661db84922c48 |
| XtQuantServer.dll | 6dc0474701691e5be22d501f92cc36c75e13d9f24781debc69fe90dfaf4b4050 |

Do not bypass the fingerprint checks to make an unsupported version run.

## Protocol evidence

The profile was derived from this installation, not from an unofficial endpoint:

- `ipcmessagequeue.dll` PackagePacker decode/encode at RVA 0x7500/0x7560 gives a
  24-byte envelope: uint64 sequence, uint32 kind, byte action, byte final flag,
  two padding bytes, uint64 session.
- `XtQuantServer.dll` dispatcher at RVA 0xf1fc maps 20005 to the stock-asset query;
  its asset `sendResponse` at 0x11410 emits kind 30001 with 0x4c (76) bytes.
- Offline SDK request objects with fictional markers confirm connection payload
  int64 session + int32 PID, and account payload int32 type + char[24]. Offline
  asset getters confirm cash/frozen/market/total offsets 28/36/44/52. The last
  16 response bytes have no verified public meaning here and are not named.
- A reference SDK session confirms the legacy file-backed `up_queue_xtquant` /
  `down_queue_<session>` route and 512-byte, 131072-slot queues with semaphore
  strategy 2. An isolated native queue round-trip preceded live requests.

Native C++ calls and mappings are confined to the child process. The native
runtime can print diagnostics at teardown; the parent accepts exactly one marked
worker result and never passes those diagnostics into the Agent JSON stream.

## Validation boundary

On 2026-10-31, a local read-only check compared all six fields with a reference
SDK query through CLI, RPC and JSONL under Python 3.14.7; all matched. No xtquant
module was imported in that Python 3.14 process. No order was submitted or
cancelled. Account identifiers and financial values are excluded from committed
fixtures and receipts. This is one build/account snapshot, not cross-broker or
all-version certification. MCP dispatch/session coverage is offline.

Run the portable offline suite with `uv run --extra dev pytest -q`; tests never
need a broker install. The native runtime itself remains Windows-only.
