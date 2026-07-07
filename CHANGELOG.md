# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog style, and this project uses semantic versioning once releases
begin.

## Unreleased

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
