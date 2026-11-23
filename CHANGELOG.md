# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog style, and this project uses semantic versioning once releases
begin.

## Unreleased

- `qmtcli buy`, `sell` and `cancel` now go through the strategy bridge, the same way `qmtcli account`
  reads do. They used to call `XtQuantTrader.order_stock` in-process, which is the route that cannot
  connect to full QMT (the -1/-12 failure). The bridge already exposed `POST /api/order/buy|sell` and
  `/api/order/cancel_by_id`; only the client side was missing. The rpc/server surface routes the same
  three commands through the bridge too, so one command no longer means two behaviours.

- Fixed `/api/order/status` and `/api/trade/status` returning empty on an account that had orders and
  fills. `_query_orders` and `_query_trades` passed `'qmt'` as `get_trade_detail_data`'s fourth
  argument, which is `strategyName`, so the result set was filtered to a strategy that does not exist.
  Measured against the live client: no fourth argument returns the order, `'qmt'` returns `[]`.

- `qmtcli bootstrap --apply` now installs the whole bridge, not just the entry point. It deploys all
  five files `connection.json` pins by sha256 into `resource_dir` and retargets their digests, so a
  new host no longer needs four hand-copied assets and a manual digest edit. The `bridge_assets`
  step fails when a deployed file differs from the repository or when its digest is not pinned,
  which is the case that made the strategy refuse to start. When `connection.json` is absent,
  `--apply` runs `qmtcli-rs setup` first, so a fresh host is one command plus the GUI login and
  strategy registration that only a human can do. The secret is still owned by setup.

- Fixed the codec crash on native types that expose `__name__` but not `__module__`. `_encode` read
  `type(value).__module__` unguarded, so such a metaclass raised `AttributeError` and the whole call
  failed. The new `result_encoding_failed` code named the missing attribute (`__module__`) but not the
  layer; `getattr(type(value), '__module__', '')` now matches how the codec already degrades on
  unreadable fields. The module string only picks the pandas and numpy branches, so an empty value
  just skips them.

- Gave a codec failure its own bridge error. `Service.encode` now reports
  `result_encoding_failed` with the offending type name instead of letting `daqmt_api.py` collapse it
  into `native_call_failed`. Until now an operator could not tell "QMT refused the call" from "the
  bridge cannot represent this result" while debugging `sdk-call`, and the two point at different
  layers. The codec's own `TypeError` message already carries the type name, so no native text is
  exposed beyond it.

- Pinned the ruff rule set in `pyproject.toml`. `AGENTS.md` and `README.md` both tell an agent to run
  `ruff check .` as the first command, but an unpinned ruff reported 266 findings on a clean tree
  (96 in `src`/`tests`/`bridge` alone), so the command could not tell a new problem from an old one.
  The selection is now explicit: ruff's four core families plus `PLW1510` (subprocess without an
  explicit `check=`), `RUF059` (unpacked but unused) and `PLR0124` (self-comparison). The ten
  findings those extras raised are fixed rather than suppressed.

- Documented which copy of the bridge the QMT client actually loads. `connection.json` pins a sha256
  per asset and the strategy refuses to start on a mismatch, so editing `bridge/*.py` changed nothing
  while editing the deployed copy without updating those digests would have broken the next start.
  `bridge/README.md` and the `AGENTS.md` code map now say so.

- Added `qmtcli market sectors|stocks|instrument`, read-only market data through the strategy
  bridge inside the full QMT client (`bridge/daqmt_server.py`). It does not import `xtquant`, so it
  is the one market path that still answers where `xtquant` cannot connect to full QMT. Every call
  raises `BridgeError` instead of returning empty data, so "no such record" stays distinguishable
  from "the bridge did not answer". Verified live against `127.0.0.1:9001`: root and nested sector
  expansion, 5000+ code sector lists, and contract details for `600000.SH` / `000001.SZ`.

- Added `qmtcli account asset|positions|orders|trades`, the bound account read on the bridge's
  fixed GET endpoints. It needs no `--account`: the strategy is bound to one account at start and
  the bridge rejects a mismatch. This is the path that works where the generic `sdk-call` route
  fails, because the bridge's own converters build these shapes instead of the codec, which only
  reads `m_`-prefixed fields. Verified live: cash 10212625.85, total asset 13699622.85, 11
  holdings, and empty orders/trades on a day with no orders.

- Added `scripts/bridge_scan.py`, the same four-rule trend screen ported off the frozen TDX feed
  onto bridge bars: one full-market tick call plus 26 daily bars in 300-symbol chunks, ranked by
  percentile. The report names its own data date from the tick timetag, so a stale feed shows up
  instead of repeating yesterday. Two gaps against the TQ version: the bridge exposes no instrument
  names, so ST names cannot be filtered out, and the 20-day high now comes from the bar high.

- Added `scripts/bridge_watch.py`, a read-only loopback probe that prints available cash, every
  holding and a live tick per symbol with its `timetag`. It exists because the TDX/TQ feed on this
  host stopped at 2026-11-09 while the bridge kept serving the same session's data, so a watch built
  on TQ reported a stale date without failing. Every endpoint it calls is a GET; it cannot place or
  cancel an order.

- Gave `QMTGateway` an explicit connection state. `connection_state()` returns `not_connected`,
  `connected_without_account` or `connected`; the two `RuntimeError` messages for a missing trader
  and a missing account now name the missing precondition instead of sharing one "is not connected"
  line; and `status` gained a `state` field (`sdk_ready` / `sdk_missing`) beside the unchanged
  `xtquant` boolean. `connect(subscribe=False)` deliberately leaves `account` unset, so the old
  message sent callers to reconnect rather than to subscribe. `a5f1dae`.

- Add opt-in `asset --backend native` through CLI/RPC/JSONL/MCP: a read-only,
  version-pinned MiniQMT IPC asset query verified on Python 3.14 without xtquant.
  SDK behavior remains the default; other commands do not gain a native backend.
- Defer data-token initialization in RPC/JSONL/MCP until a non-native request,
  preserving native-only sessions without SDK dependencies.
- Restored `buy`, `sell` and `cancel` on the CLI, `rpc` and `server` transports, and lifted the
  `trade-call` restriction back to blocking only `_`-prefixed methods. `ad500c6` had removed them
  after a 2026-10-19 unconfirmed 000963 sell order; an operator decision on 2026-11-08 restored them,
  with per-order human confirmation kept in the calling gateway (KATANA) rather than in qmtcli.
  The MCP tool surface is unchanged by this: `mcp_server.py` still excludes every `places_order` /
  `cancels_order` capability, so an MCP client cannot place an order.
- Added `scripts/check_mcp_tree.py`, a local guard that fails when the qmt MCP server serves a
  checkout other than this one or a different command surface, plus `docs/repo-map.md` naming the
  four copies of the project on this machine and the order policy each carries.
- Removed a host-dependent offline test that could discover a real QMT SDK and
  initialize its trader; deterministic fake-SDK and error-envelope coverage remains.
- Updated locked urllib3 to 2.8.0 and certifi to 2026.10.19 for transport security
  fixes, retaining the unaffected emSign roots in the certificate bundle.
- Updated locked MCP to 1.30.0 and PyJWT to 2.15.0 for security fixes in the
  optional MCP dependency graph.
- Updated the locked AnyIO dependency from 4.14.1 to 4.14.2 for security fixes in the
  optional MCP dependency graph.
- Isolated offline tests from an inherited `QMTCLI_XTDC_TOKEN`; token-specific tests still set
  their own values, without changing the CLI's environment-variable fallback.
- Normalize native and numpy missing values to JSON `null` across CLI, RPC, server
  streams and MCP tool output, including tuple and converted SDK/object payloads.
  Preserve finite values and pandas index representation.

## 0.4.0 - 2026-07-07

- Added `qmtcli mcp`: a stdio MCP (Model Context Protocol) server exposing qmtcli commands as MCP
  tools. Capabilities-driven, single source of truth: tools are generated from
  `AGENT_CAPABILITIES` as `qmt_<name>` (dashes become underscores, for example `qmt_full_tick`,
  `qmt_sector_stocks`, `qmt_account_infos`), and every tool call is dispatched through the
  existing `_handle_rpc_request` rpc machinery instead of a second command registry. Excludes
  order placement/cancellation (`buy`, `sell`, `cancel`), `trade_call` (an unguarded escape hatch
  onto the full `XtQuantTrader` surface), and anything restricted to a transport list that
  excludes `rpc` (the `subscribe`/`subscribe_whole`/`unsubscribe` trio, server-only; `watch`,
  CLI-only); every other command -- `status`, `doctor`, `data_call`, `fields`, `download`, every
  named data command, and every trade query including `asset`/`positions`/`orders`/`trades` --
  becomes a tool, with shared optional `path`/`account`/`account_type` parameters added to every
  tool's input schema. Ships behind a new `mcp` optional-dependencies extra (`pip install
  'qmtcli[mcp]'` / `uv sync --extra mcp`), also added to the `dev` dependency group so tests can
  import it; `qmtcli mcp` without the extra installed prints a clean `{"ok": false, "error": "mcp
  extra is not installed; pip install 'qmtcli[mcp]'"}` and exits 1 instead of raising
  `ImportError`. Added `AGENT_CAPABILITIES`/`AGENT_SCHEMA` metadata (new `mcp` transport and
  command) and a new `tests/test_mcp_server.py`. See `src/qmtcli/mcp_server.py`.

## 0.3.0 - 2026-07-07

- Added a `sector` command family closing the last mutating-data gap in the xtdata alignment
  matrix: `sector create-folder`/`create` (`create_sector_folder`/`create_sector`, both taking
  `--parent` and an `--overwrite`/`--no-overwrite` flag pair, default `overwrite=true`), `sector
  add`/`remove-stocks`/`reset` (`add_sector`/`remove_stock_from_sector`/`reset_sector`, each taking
  one or more symbols), and `sector remove` (`remove_sector`). Each action is its own argparse
  subparser nested under `sector`, so required arguments (`--parent`, symbols) are enforced by
  argparse itself on the CLI path; the shared `_dispatch_sector_command` dispatcher raises a clear
  `ValueError` for the same conditions on the `rpc`/`server` path, which bypasses argparse. Returns
  the raw SDK result, or `{"ok": true, "action": ..., "sector": ...}` when the SDK returns `None`.
  Added a new `mutates_local_data` danger level for it.
- Added `local-data` (`xtdata.get_local_data`) and `full-kline` (`xtdata.get_full_kline`) data
  commands, matching the existing `bars` argument shape (`--fields`, `--period`, `--start`,
  `--end`, `--count`, `--dividend-type`, `--no-fill-data`); `local-data` also takes `--data-dir` and
  reads the local cache only (no service round-trip; run `download history` first), and
  `full-kline` may require a 投研 (research) edition QMT client (older broker clients return
  ErrorID 300000).
- Added a CLI-only `watch` command: `qmtcli watch SYMBOL [SYMBOL...] [--period 1m] [--whole]`
  subscribes (one `subscribe_quote` call per symbol, or a single `subscribe_whole_quote` call with
  `--whole`) and then blocks in `xtdata.run()`, streaming JSONL quote/whole_quote events to stdout
  until interrupted (`KeyboardInterrupt` is caught and mapped to a clean exit 0). It is CLI-only —
  deliberately excluded from `DATA_COMMAND_NAMES` and not reachable over `rpc`/`server`, since
  server mode already has `subscribe`/`subscribe_whole`/`unsubscribe` for the same purpose.
- Updated `AGENT_CAPABILITIES`, `AGENT_SCHEMA` (`mutates_local_data` danger level), and
  `AGENT_EXAMPLES` (`sector_add`, `watch`, `local_data`) for all of the above.
- Updated `docs/xtdata-alignment.md`: `create_sector_folder`/`create_sector`/`add_sector`/
  `remove_stock_from_sector`/`remove_sector`/`reset_sector` now map to `sector <action>` instead of
  `data-call`; `get_local_data` now maps to `local-data`; `get_full_kline` now maps to `full-kline`;
  the `subscribe_quote`/`subscribe_whole_quote` rows note the new CLI `watch` alternative; and the
  `run` row now points at `watch` instead of "not needed".
- Updated both READMEs (bilingual) with the new commands: `local-data`/`full-kline` examples, a
  new "Sector Management" example block, a new "CLI Streaming (`watch`)" section mirroring
  "Server Streaming", and a Safety Boundaries note for the new `mutates_local_data` danger level.

## 0.2.0 - 2026-07-07

- `QMTGateway.add_sdk_path` now prefers an already-importable `xtquant` (installed in the active
  environment, for example via the new `sdk` extra) and only appends — never prepends/inserts —
  the QMT-bundled `site-packages` as a fallback, so a venv's own `numpy`/`pandas` always shadow the
  older bundled copies QMT ships alongside `xtquant`. Added a `sdk` optional-dependencies extra
  (`pip install 'qmtcli[sdk]'` / `uv sync --extra sdk`) declaring `xtquant`/`pandas`/`numpy`.
  `doctor` now reports `sdk_source` (`environment` / `qmt_bundled` / `missing`) and
  `xtquant_version` (from package metadata, falling back to the module's own `__version__`).
- Wrapped all CLI data/account command execution in a clean error envelope: any exception raised
  while handling a command now prints `{"ok": false, "error": "<message>"}` and exits 1, instead of
  a raw Python traceback. argparse's own usage errors (`SystemExit`, `--help`) still propagate
  as-is, the existing `rpc`/`server` error envelopes are unchanged, and successful output keeps its
  original unwrapped ("raw") shape.
- Added 12 new named `XtQuantTrader` read-only query commands: `position-statistics`,
  `credit-detail`, `stk-compacts`, `credit-subjects`, `credit-slo-code`, `credit-assure`,
  `ipo-limit`, `com-fund`, `com-position`, `ipo-data`, `account-infos`, and `account-status`. The
  last three wrap methods that take no account argument at all, so `--account` is optional for
  them; `QMTGateway.connect()` gained a `subscribe` parameter so it can skip
  `trader.subscribe(account)` in that case while still connecting a session. Extended `orders` with
  `--cancelable-only` (`query_stock_orders(account, cancelable_only=...)`). All of the above are
  available over `rpc`/`server` too, with the same dash/underscore command-name aliasing as the
  existing named data commands. Added `docs/xttrader-alignment.md`, a coverage matrix for the
  xttrader doc page mirroring `docs/xtdata-alignment.md`.
- Added a `fields` command: static xtdata field-name reference dictionaries (`tick`, `kline`,
  `divid`, `l2quote`, `l2order`, `l2transaction`, `l2quoteaux`, `l2orderqueue`, `balance`,
  `income`, `cashflow`, `pershareindex`, `capital`, `top10holder`, `holdernum`, `instrument`)
  extracted from the doc appendix by the new `scripts/extract_doc_fields.py`, shipped as
  `src/qmtcli/xtdata_fields.json`. Fully offline — `fields` never calls into `QMTGateway`/`xtdata`.
  `qmtcli fields` with no argument lists the available kinds and their titles.
- Added experimental standalone xtdatacenter (xtdc) data mode: `--xtdc-token` (env fallback
  `QMTCLI_XTDC_TOKEN`) plus `--xtdc-port` (default `58620`) make `qmtcli` call
  `xtquant.xtdatacenter.set_token()`/`.init()` once, idempotently, before running any command via
  the new `QMTGateway.init_xtdc()` classmethod. `doctor` reports whether
  `xtquant.xtdatacenter` is importable as `xtdc_available`.
- Added `scripts/check_doc_drift.py` and a weekly (plus manually-dispatchable)
  `.github/workflows/doc-drift.yml` GitHub Action: extracts function names from the live
  xtdata/xttrader doc pages and checks that every one is reflected somewhere in the alignment
  matrices, filing a GitHub issue (deduplicated by title) when a doc function is missing. A
  network fetch failure prints a warning and exits 0 instead of false-alarming the schedule.
- Added a "Runtime caveats" section to `docs/xtdata-alignment.md` covering: function availability
  depending on the broker QMT client build/edition regardless of SDK version (for example
  `get_period_list` returning a server "function not realize" error on some broker builds); the
  `sdk` extra vs. bundled-SDK tradeoff; getters that return empty until the matching `download`
  command has populated the local cache; and the xtdc experimental note.
- Updated `AGENT_CAPABILITIES` and `AGENT_EXAMPLES` for all of the above.
- Updated both READMEs for the `sdk` extra, `fields`, the new trade query commands, standalone xtdc
  mode, and the doc-drift CI check.
- Made `_json_default` pandas/numpy-aware: DataFrames (and nested dict-of-DataFrame results such
  as `get_market_data_ex`/`get_financial_data`) are serialized as JSON records instead of dumping
  internal `BlockManager`/`__dict__` state, a non-`RangeIndex` (typically a time index) is kept as
  a plain column, Series become plain objects, and NaN/`pd.NaT`/`pd.NA`/numpy scalars and arrays
  are converted to valid JSON instead of the non-standard `NaN` token or raw numpy repr. Added a
  `pandas`/`numpy` `dev` dependency group (`[dependency-groups]`, uv's default-installed group) so
  `uv run pytest` picks them up without needing `--extra dev`.
- Extended `rpc`/`server` to route every named data command (`calendar`, `bars`, `sector-stocks`,
  `download`, ...) through the same dispatch the CLI uses, accepting either the dashed CLI command
  name or its underscore alias (for example `sector_stocks`) and the CLI's own parameter names as
  JSON fields. Missing required parameters now raise a clear `{"ok": false, "error": "<command>
  requires <param>"}` instead of only being caught by argparse on the CLI side.
- Added server-mode subscription streaming: `subscribe`, `subscribe_whole`, and `unsubscribe` wrap
  `xtdata.subscribe_quote`/`subscribe_whole_quote`/`unsubscribe_quote`; quote pushes print as
  extra JSONL lines with an `event` field, interleaved with normal `{"ok": ...}` responses through
  a shared print lock. These three only work in `server` mode; the one-shot `rpc` command and the
  CLI reject them with `"subscribe commands require server mode"`.
- Fixed `calendar` to call `xtdata.get_trading_calendar` with the required `market` argument
  (previously called with zero arguments and always failed).
- Fixed `l2-quote`, `l2-order`, and `l2-transaction` argument mapping: symbols were being passed
  into the `field_list` slot instead of `stock_code`; these now take a single required symbol plus
  `--fields`/`--start`/`--end`/`--count` options matching the real `get_l2_quote`/`get_l2_order`/
  `get_l2_transaction` signatures. `l2-quote` no longer accepts multiple symbols (breaking change,
  but the previous multi-symbol form never worked correctly).
- Documented and extended `bars` inputs to match `xtdata.get_market_data_ex`: added
  `--fields`, `--start`, `--end`, `--dividend-type`, and `--no-fill-data`.
- Added new read-only data commands: `instrument-detail`, `instrument-type`, `trading-dates`,
  `divid-factors`, `holidays`, `period-list`, `ipo-info`, `cb-info`, `etf-info`, `index-weight`,
  and `financials`.
- Added a new `download` command (`history`, `financials`, `sectors`, `index-weight`, `cb`, `etf`,
  `holidays`, `history-contracts` targets) for populating the local QMT cache via the `download_*`
  xtdata functions, with a new `downloads_data` danger level.
- Updated `AGENT_CAPABILITIES`/`AGENT_SCHEMA` metadata for all of the above, including a note that
  the L2 commands require Level-2 data permission and are not covered by the public xtdata doc page.
- Added `docs/xtdata-alignment.md`, a full coverage matrix mapping every function on the official
  xtdata doc page to its `qmtcli` CLI command (or `data-call`/not exposed).
- Added generated README hero image.
- Split documentation into English `README.md` and Chinese `README.zh-CN.md`.
- Added generic agent compatibility wording, README architecture image, and demo GIF storyboard.
- Added README badges, first-screen demo, Chinese positioning, and generic local-agent tool example.
- Repositioned README and package metadata around the AI/agent-first QMT trading bridge use case.
- Expanded README with commands, JSON RPC examples, safety boundaries, and QMT path notes.
- Added example JSON/JSONL automation files.
- Added contributing notes and GitHub Actions test workflow.
- Improved CLI help for command-specific usage.

## 0.1.0

- Initial local QMT/XtQuant CLI bridge.
