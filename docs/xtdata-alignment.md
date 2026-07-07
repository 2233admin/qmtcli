# xtdata Alignment Matrix

Source: [https://dict.thinktrader.net/nativeApi/xtdata.html](https://dict.thinktrader.net/nativeApi/xtdata.html)

Checked: 2026-07-07, against `xtquant` 250516.1.1.

This table maps every function documented on the xtdata doc page to its `qmtcli` CLI surface. Where
a function is not exposed as a named command, it can still be called through the generic
`data-call` (read/query) or `trade-call` (trader) escape hatches, at the caller's own risk — no
argument validation beyond blocking private (`_`-prefixed) method names.

| xtdata function | doc section (Chinese) | CLI command | notes |
| --- | --- | --- | --- |
| `subscribe_quote` | 订阅单股行情数据 | `subscribe` (server mode only); also `watch` (CLI, streaming) | quote pushes print as extra JSONL lines with an `event` field; rejected outside `server` mode on the `rpc`/CLI path |
| `subscribe_whole_quote` | 订阅全推行情数据 | `subscribe_whole` (server mode only); also `watch --whole` (CLI, streaming) | quote pushes print as extra JSONL lines with an `event` field; rejected outside `server` mode on the `rpc`/CLI path |
| `unsubscribe_quote` | 反订阅行情数据 | `unsubscribe` (server mode only) | rejected outside `server` mode |
| `run` | 阻塞当前线程进入订阅监听 | `watch` | the CLI `watch` command subscribes then calls `run` directly, blocking until Ctrl+C (`KeyboardInterrupt` is caught and mapped to a clean exit 0); the `server` JSONL loop still doesn't need `run` since it already blocks reading stdin while xtquant fires subscribe callbacks on their own thread |
| `subscribe_formula` | 订阅公式数据 | not exposed | callback/long-running API; use `data-call` at own risk |
| `unsubscribe_formula` | 反订阅公式数据 | not exposed | callback/long-running API; use `data-call` at own risk |
| `call_formula` | 计算公式数据 | not exposed | callback/long-running API; use `data-call` at own risk |
| `call_formula_batch` | 批量计算公式数据 | not exposed | callback/long-running API; use `data-call` at own risk |
| `generate_index_data` | 生成板块指数数据 | not exposed | callback/long-running API; use `data-call` at own risk |
| `get_market_data` | 获取行情数据(老接口) | `bars` | `bars` calls `get_market_data_ex`, a superset with the same field/period/time/count/dividend_type/fill_data shape |
| `get_market_data_ex` | 获取行情数据 | `bars` | full field/period/start/end/count/dividend_type/fill_data mapping |
| `get_local_data` | 获取本地行情数据 | `local-data` | reads local cache only, no service round-trip; run `download history` first to populate the cache |
| `get_full_tick` | 获取全推数据 | `full-tick` | already correct before this change |
| `get_divid_factors` | 获取除权除息数据 | `divid-factors` | |
| `download_history_data` | 下载历史行情数据(单股) | `data-call` | not exposed as a named command; use `download history` (below) for the batch form |
| `download_history_data2` | 下载历史行情数据(多股) | `download history` | callback is not exposed; only `incrementally` is passed through |
| `download_history_contracts` | 下载合约信息 | `download history-contracts` | |
| `get_holidays` | 获取节假日列表 | `holidays` | |
| `get_trading_calendar` | 获取交易日历 | `calendar` | `market` is required by the SDK; the CLI now enforces this |
| `download_cb_data` | 下载可转债数据 | `download cb` | |
| `get_cb_info` | 获取可转债信息 | `cb-info` | |
| `get_ipo_info` | 获取新股申购信息 | `ipo-info` | |
| `get_period_list` | 获取周期列表 | `period-list` | |
| `download_etf_info` | 下载 ETF 信息 | `download etf` | |
| `get_etf_info` | 获取 ETF 信息 | `etf-info` | |
| `download_holiday_data` | 下载节假日数据 | `download holidays` | |
| `get_full_kline` | 获取全推 K 线数据 | `full-kline` | may require a 投研 (research) edition QMT client; older broker clients return ErrorID 300000 |
| `get_financial_data` | 获取财务数据 | `financials` | |
| `download_financial_data` | 下载财务数据 | `download financials` | `download_financial_data2` variants are not separately exposed |
| `get_instrument_detail` | 获取合约信息 | `instrument-detail` | `iscomplete` maps to `--complete` |
| `get_instrument_type` | 获取合约类型 | `instrument-type` | |
| `get_trading_dates` | 获取交易日期 | `trading-dates` | |
| `get_sector_list` | 获取板块列表 | `sector-list` | already correct before this change |
| `get_stock_list_in_sector` | 获取板块成分股 | `sector-stocks` | already correct before this change |
| `download_sector_data` | 下载板块数据 | `download sectors` | |
| `create_sector_folder` | 创建板块目录 | `sector create-folder` | mutates local custom sectors; `danger: mutates_local_data` |
| `create_sector` | 创建自定义板块 | `sector create` | mutates local custom sectors; `danger: mutates_local_data` |
| `add_sector` | 板块增加成分股 | `sector add` | mutates local custom sectors; `danger: mutates_local_data` |
| `remove_stock_from_sector` | 板块剔除成分股 | `sector remove-stocks` | mutates local custom sectors; `danger: mutates_local_data` |
| `remove_sector` | 删除自定义板块 | `sector remove` | mutates local custom sectors; `danger: mutates_local_data` |
| `reset_sector` | 重置板块 | `sector reset` | mutates local custom sectors; `danger: mutates_local_data` |
| `get_index_weight` | 获取指数权重 | `index-weight` | |
| `download_index_weight` | 下载指数权重 | `download index-weight` | |

## Level-2 commands (not on the doc page)

`l2-quote`, `l2-order`, and `l2-transaction` wrap `get_l2_quote`, `get_l2_order`, and
`get_l2_transaction`. These functions require Level-2 market data permission from the broker and are
not documented on the public xtdata doc page above; they are included here because they existed in
the CLI before this change (with a broken argument mapping, now fixed to a single `stock_code`
string plus `field_list`/`start_time`/`end_time`/`count`).

## Runtime caveats

- **Function availability depends on the broker QMT client build/edition, not just the SDK
  version.** A function can be present and callable in `xtquant` and still fail at runtime because
  the broker's QMT client build doesn't implement it server-side. For example, `get_period_list` on
  a 2024-era broker build has been observed to return a server error (`ErrorID 300000`, "function
  not realize") even when the local `xtquant` SDK is current. Treat any such error as a broker/build
  limitation, not a `qmtcli` bug — there is no client-side workaround.
- **Prefer a venv/pip SDK install over the bundled one.** Install with the `sdk` extra
  (`pip install 'qmtcli[sdk]'` or `uv sync --extra sdk`) so `xtquant`/`pandas`/`numpy` come from the
  active environment instead of the QMT install's bundled `site-packages`. `qmtcli` now resolves
  `xtquant` from the environment first and only falls back to (and appends, never prepends) the
  bundled QMT `site-packages` path if nothing is already importable — see `QMTGateway.add_sdk_path`.
  The bundled SDK works but can be noticeably older than the current doc pages (for example, older
  bundled copies have been observed to lack `get_period_list` entirely) and its bundled `numpy` can
  conflict with a host Python's own `numpy` if it were ever given priority. `qmtcli doctor` reports
  which source won as `sdk_source`: `environment`, `qmt_bundled`, or `missing`.
- **Some getters return empty until the matching `download` command has been run.** `holidays`,
  `bars`/historical K-line data, and similar local-cache-backed getters can return empty results on
  a fresh QMT install until the corresponding `download` target (`download holidays`,
  `download history <symbols>`, ...) has populated the local cache at least once.
- **`--xtdc-token` / xtdatacenter standalone data mode is experimental.** Setting `--xtdc-token` (or
  `QMTCLI_XTDC_TOKEN`) makes `qmtcli` call `xtquant.xtdatacenter.set_token()` then `.init()` before
  running any command, so `xtdata` calls can route through the standalone 迅投投研 data service
  instead of a local QMT client. This requires a valid 迅投投研 data token and has been verified only
  as far as `init()` succeeding, not end-to-end against real data — `--xtdc-port` is accepted for
  future use but is not yet wired to a specific xtdatacenter call. `qmtcli doctor` reports whether
  the `xtquant.xtdatacenter` module itself is importable as `xtdc_available`.
