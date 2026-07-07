# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog style, and this project uses semantic versioning once releases
begin.

## Unreleased

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
