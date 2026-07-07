# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog style, and this project uses semantic versioning once releases
begin.

## Unreleased

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
