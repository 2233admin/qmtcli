# qmtcli

[![tests](https://github.com/2233admin/qmtcli/actions/workflows/test.yml/badge.svg)](https://github.com/2233admin/qmtcli/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

[中文](README.md) | English

Local JSON CLI for QMT / miniQMT and the bundled XtQuant SDK.

`qmtcli` is a small bridge between a logged-in local QMT client and tools that prefer process I/O:
agents, scripts, schedulers, notebooks, or other automation. It exposes diagnostics, market data,
account queries, and guarded stock order commands over stable JSON stdin/stdout.

![qmtcli local JSON bridge](docs/assets/qmtcli-hero.png)

`qmtcli` does not install QMT, store credentials, bypass broker risk checks, or run a network
service. QMT must already be installed and logged in locally.

## Quick Demo

Discover the command surface:

```powershell
qmtcli capabilities
qmtcli schema
qmtcli examples
```

Run one JSON request:

```powershell
Get-Content examples\status.json | qmtcli rpc
```

Run a JSONL loop for an agent or script:

```powershell
qmtcli server
```

Response shape:

```json
{"ok":true,"data":{}}
```

Error shape:

```json
{"ok":false,"error":"message"}
```

If a request includes `id`, the response echoes it.

## Why

QMT bundles `xtquant` inside the broker client install. That is fine for direct Python scripts on a
trading machine, but awkward for agents and process-based automation. `qmtcli` keeps the QMT
integration local and gives callers a simple JSON contract:

- `capabilities`, `schema`, and `examples` for discovery;
- `rpc` for one request over stdin/stdout;
- `server` for newline-delimited JSON requests;
- explicit labels for read-only calls, escape hatches, order placement, and cancellation;
- tests that fake `xtquant`, so CI does not need a broker install.

Any runtime that can start a local process and exchange JSON can use it — Python, Rust, Go,
Node.js, shell scripts, or an LLM agent, no language-specific SDK or binding required.

## Features

- QMT SDK discovery from common Windows install paths, preferring an already-installed venv/pip
  `xtquant` over the QMT-bundled copy (see [Install](#install)).
- `status` and `doctor` diagnostics, including SDK source (`environment` / `qmt_bundled` /
  `missing`), `xtquant` version, and xtdc availability.
- Market data commands: calendar, trading dates, sectors, ticks, bars, local cached bars
  (`local-data`), full-push K-line (`full-kline`), L2 data, instrument/ETF/CB/IPO/index-weight
  metadata, and financials.
- `sector` command family for creating, populating, and deleting local custom sectors
  (`create-folder`, `create`, `add`, `remove-stocks`, `remove`, `reset`).
- `watch`: CLI-only live quote streaming (JSONL to stdout) via `subscribe_quote`/
  `subscribe_whole_quote`, blocking until Ctrl+C — see [CLI Streaming](#cli-streaming-watch).
- `mcp`: stdio MCP server exposing qmtcli commands as MCP tools, generated from
  `AGENT_CAPABILITIES` — see [MCP Server](#mcp-server).
- `fields`: static xtdata field-name reference dictionaries (tick, kline, balance, ...) extracted
  from the doc appendix. Fully offline, no QMT install needed.
- pandas-aware JSON output: DataFrames/Series returned by xtdata are serialized as records (a time
  index is kept as a plain column), and NaN/NaT/`pd.NA`/numpy scalars all become plain JSON values
  instead of invalid `NaN` tokens or unreadable object dumps.
- `download` command for populating the local QMT cache (history, financials, sectors, index
  weight, convertible bonds, ETF info, holidays, contracts).
- Account queries: asset, positions, orders (with `--cancelable-only`), trades.
- Trader query commands: position statistics, credit/margin queries, IPO quota and data, account
  infos/status, and ordinary-account fund/position queries — see
  [Trade Query Commands](#trade-query-commands).
- Fixed-price A-share `buy`, `sell`, and `cancel`.
- Generic `data-call` for public `xtquant.xtdata` methods.
- Generic `trade-call` for public `XtQuantTrader` methods.
- Optional standalone xtdatacenter (xtdc) data mode via `--xtdc-token` (experimental) — see
  [Standalone Data Mode](#standalone-data-mode-xtdc-experimental).
- Agent/script protocol commands: `capabilities`, `schema`, `examples`, `rpc`, `server`.
- A scheduled `doc-drift` GitHub Action (weekly, plus manual dispatch) re-checks the alignment
  matrices below against the live doc pages and files an issue if a new doc function is not yet
  reflected in either matrix; see `scripts/check_doc_drift.py`.

See [`docs/xtdata-alignment.md`](docs/xtdata-alignment.md) and
[`docs/xttrader-alignment.md`](docs/xttrader-alignment.md) for the full function-to-command
coverage matrices against the official
[xtdata](https://dict.thinktrader.net/nativeApi/xtdata.html) and
[xttrader](https://dict.thinktrader.net/nativeApi/xttrader.html) docs.

## Install

Recommended: install with the `sdk` extra so `xtquant`/`pandas`/`numpy` come from this environment
instead of QMT's bundled `site-packages`; the broker QMT client then only needs to provide the
local trading/data service, not the Python SDK itself:

```powershell
uv sync --extra dev --extra sdk
pip install -e ".[dev,sdk]"
```

Bundled-SDK fallback (no `sdk` extra) still works — `qmtcli` falls back to the QMT install's own
`xtquant`/`numpy`/`pandas` when nothing is already importable — but the bundled copy can be older
than the current docs (for example, some bundled builds lack `get_period_list`) and its bundled
`numpy` should never be allowed to shadow a venv's own `numpy`. `qmtcli doctor` reports which
source won as `sdk_source`. See [Runtime caveats](docs/xtdata-alignment.md#runtime-caveats) for
details.

For local development:

```powershell
uv sync --extra dev
uv run qmtcli status
```

Editable pip install:

```powershell
pip install -e .[dev]
qmtcli status
```

## Agent And Script Usage

Discovery:

```powershell
qmtcli capabilities
qmtcli schema
qmtcli examples
```

One-shot RPC:

```powershell
Get-Content examples\status.json | qmtcli rpc
Get-Content examples\data_call.json | qmtcli rpc
```

JSONL loop:

```powershell
.\examples\jsonl_server.ps1
```

Generic integration notes are in [`examples/agent_tool.md`](examples/agent_tool.md). A short demo
recording script is in [`docs/demo_storyboard.md`](docs/demo_storyboard.md).

All named data commands (`calendar`, `bars`, `sector-stocks`, `download`, ...) are available over
`rpc`/`server` too, not just the CLI; send their CLI parameter names as JSON fields, for example
`{"command":"bars","symbols":["600519.SH"],"period":"1d"}`. The command name accepts either dashes
or underscores (`sector-stocks` or `sector_stocks`).

## Server Streaming

In `server` mode only, `subscribe`, `subscribe_whole`, and `unsubscribe` wrap the callback-based
`xtdata.subscribe_quote`, `subscribe_whole_quote`, and `unsubscribe_quote`:

```json
{"command":"subscribe","symbol":"600519.SH","period":"1d"}
{"command":"subscribe_whole","symbols":["600519.SH","000001.SZ"]}
{"command":"unsubscribe","seq":1}
```

Subscribing responds with `{"ok":true,"data":{"seq":1}}`, and every later quote push from xtquant
is printed as its own JSONL line carrying an `event` field instead of `ok`, interleaved with normal
responses on the same stdout stream:

```json
{"ok":true,"data":{"seq":1}}
{"event":"quote","seq":1,"symbol":"600519.SH","data":{"600519.SH":{"lastPrice":1500.0}}}
```

The one-shot `rpc` command and the CLI reject subscribe commands with `{"ok":false,"error":
"subscribe commands require server mode"}`, since a subscription only makes sense while `server`
keeps the process alive.

## CLI Streaming (`watch`)

`watch` is a CLI-only alternative to `server`-mode `subscribe`/`subscribe_whole`: it subscribes
directly, then blocks in `xtdata.run()`, printing one JSONL line per quote push until interrupted
(Ctrl+C exits cleanly with code 0). It is not available over `rpc`/`server`.

```powershell
qmtcli watch 600519.SH
qmtcli watch 600519.SH 000001.SZ --period 1m
qmtcli watch 600519.SH 000001.SZ --whole
```

```json
{"event":"quote","symbol":"600519.SH","data":{"600519.SH":{"lastPrice":1500.0}}}
```

## MCP Server

`qmtcli mcp` runs a stdio MCP (Model Context Protocol) server exposing qmtcli commands as MCP
tools. Capabilities-driven, single source of truth: tools are generated from
`AGENT_CAPABILITIES`, and every tool call is dispatched through the same rpc machinery as
`rpc`/`server` — there is no second command registry.

Install the `mcp` extra:

```powershell
uv sync --extra mcp
```

Run it directly (talks JSON-RPC over stdio; nothing else prints to stdout):

```powershell
qmtcli mcp
```

Register it with Claude Code:

```powershell
claude mcp add qmt -- uv run --directory D:/projects/qmtcli --extra mcp qmtcli mcp
```

Tool names are `qmt_<name>` with dashes replaced by underscores, for example `qmt_full_tick`,
`qmt_sector_stocks`, `qmt_account_infos`. There is no persistent `--account`/`--path` like the
CLI has — every trade-query/account tool takes optional `path`/`account`/`account_type`
arguments per call instead.

Excluded by design: `buy`, `sell`, `cancel` (order placement/cancellation) and `trade_call` (an
unguarded escape hatch onto the full `XtQuantTrader` surface) — use the CLI directly for guarded
trading. `watch` and the `subscribe`/`subscribe_whole`/`unsubscribe` trio are also excluded (CLI-
only / server-only streaming, not a fit for one-shot tool calls). Everything else — `status`,
`doctor`, `data_call`, `fields`, `download`, every named data command, and every trade query
(`asset`, `positions`, `orders`, `trades`, ...) — is available.

Without the `mcp` extra installed, `qmtcli mcp` prints
`{"ok":false,"error":"mcp extra is not installed; pip install 'qmtcli[mcp]'"}` and exits 1.

## QMT Paths

Pass either a QMT install root or its `userdata_mini` directory:

```powershell
qmtcli --path D:\DFZQxtqmt_client_real_win64 doctor
qmtcli --path D:\DFZQxtqmt_client_real_win64\userdata_mini --account ACCOUNT_ID asset
```

When `--path` is omitted, these roots are checked:

- `D:\DFZQxtqmt_client_real_win64`
- `D:\DFZQxtqmt_client_test_win64`
- `C:\DFZQxtqmt_client_real_win64`
- `C:\DFZQxtqmt_client_test_win64`

Expected SDK location:

```text
<QMT root>\bin.x64\Lib\site-packages\xtquant
```

## Common Commands

Diagnostics:

```powershell
qmtcli status
qmtcli doctor
python -m qmtcli status
```

Market data:

```powershell
qmtcli calendar SH
qmtcli trading-dates SH --count 5
qmtcli sector-list
qmtcli sector-stocks 沪深A股
qmtcli full-tick 600519.SH 000001.SZ
qmtcli bars 600519.SH --period 1d --count 100
qmtcli local-data 600519.SH --period 1d --count 100
qmtcli full-kline 600519.SH --period 1m
qmtcli instrument-detail 600519.SH
qmtcli instrument-type 600519.SH
qmtcli divid-factors 600519.SH
qmtcli holidays
qmtcli period-list
qmtcli ipo-info
qmtcli cb-info 123001.SZ
qmtcli etf-info
qmtcli index-weight 000300.SH
qmtcli financials 600519.SH --tables Balance
```

Static field-name reference dictionaries (fully offline, no QMT install needed):

```powershell
qmtcli fields
qmtcli fields tick
qmtcli fields balance
```

L2 commands require Level-2 market data permission from the broker and are not covered by the
public xtdata doc page:

```powershell
qmtcli l2-quote 600519.SH
qmtcli l2-order 600519.SH
qmtcli l2-transaction 600519.SH
```

Download data into the local QMT cache; these calls return once the SDK download finishes and do
not print market data themselves — use the read commands above for that:

```powershell
qmtcli download history 600519.SH --period 1d
qmtcli download financials 600519.SH --tables Balance
qmtcli download sectors
qmtcli download index-weight
qmtcli download cb
qmtcli download etf
qmtcli download holidays
qmtcli download history-contracts
```

Manage local custom sectors (mutates local sector definitions only; `danger: mutates_local_data`):

```powershell
qmtcli sector create-folder MyGroup --parent 我的自定义板块
qmtcli sector create MySector --parent 我的自定义板块
qmtcli sector add MySector 600519.SH 000001.SZ
qmtcli sector remove-stocks MySector 600519.SH
qmtcli sector reset MySector 600519.SH
qmtcli sector remove MySector
```

Account and order commands require `--account`:

```powershell
qmtcli --account ACCOUNT_ID asset
qmtcli --account ACCOUNT_ID positions
qmtcli --account ACCOUNT_ID orders
qmtcli --account ACCOUNT_ID orders --cancelable-only
qmtcli --account ACCOUNT_ID trades
qmtcli --account ACCOUNT_ID buy 600519.SH 100 1500.00
qmtcli --account ACCOUNT_ID sell 600519.SH 100 1500.00
qmtcli --account ACCOUNT_ID cancel ORDER_ID
```

## Trade Query Commands

These wrap named `XtQuantTrader` query methods; see
[`docs/xttrader-alignment.md`](docs/xttrader-alignment.md) for the full mapping. Most require
`--account`:

```powershell
qmtcli --account ACCOUNT_ID position-statistics
qmtcli --account ACCOUNT_ID credit-detail
qmtcli --account ACCOUNT_ID stk-compacts
qmtcli --account ACCOUNT_ID credit-subjects
qmtcli --account ACCOUNT_ID credit-slo-code
qmtcli --account ACCOUNT_ID credit-assure
qmtcli --account ACCOUNT_ID ipo-limit
qmtcli --account ACCOUNT_ID com-fund
qmtcli --account ACCOUNT_ID com-position
```

`ipo-data`, `account-infos`, and `account-status` wrap `XtQuantTrader` methods that take no account
argument at all, so `--account` is optional for these three — `qmtcli` still connects a QMT
session, it just skips subscribing an account:

```powershell
qmtcli ipo-data
qmtcli account-infos
qmtcli account-status
```

## Escape Hatches

`data-call` calls any public method on `xtquant.xtdata`:

```powershell
qmtcli data-call get_stock_list_in_sector --args "[\"沪深A股\"]"
qmtcli data-call get_cb_info --args "[\"123001.SZ\"]"
```

`trade-call` calls any public method on `XtQuantTrader` after connecting the account. By default,
the `StockAccount` object is prepended to positional arguments:

```powershell
qmtcli --account ACCOUNT_ID trade-call query_stock_orders
qmtcli --account ACCOUNT_ID trade-call some_method --args "[1,2]" --kwargs "{\"flag\":true}"
qmtcli --account ACCOUNT_ID trade-call method_without_account --no-account
```

Private method names beginning with `_` are blocked.

## Standalone Data Mode (xtdc, experimental)

`--xtdc-token` (or the `QMTCLI_XTDC_TOKEN` environment variable) enables standalone xtdatacenter
data mode: before running any command, `qmtcli` calls `xtquant.xtdatacenter.set_token()` and
`.init()`, so `xtdata` calls can route through the 迅投投研 standalone data service instead of a
local QMT client:

```powershell
$env:QMTCLI_XTDC_TOKEN = "YOUR_TOKEN"
qmtcli calendar SH

qmtcli --xtdc-token YOUR_TOKEN --xtdc-port 58620 calendar SH
```

This requires a valid 迅投投研 data token and is **experimental** — verified only as far as `init()`
succeeding, not end-to-end against real data. `--xtdc-port` is accepted (default `58620`) but not
yet wired to a specific xtdatacenter call. `qmtcli doctor` reports whether the
`xtquant.xtdatacenter` module itself is importable as `xtdc_available`. See
[Runtime caveats](docs/xtdata-alignment.md#runtime-caveats) for more.

## JSON Request Examples

```json
{"command":"status"}
{"command":"data_call","method":"get_stock_list_in_sector","args":["沪深A股"]}
{"command":"buy","account":"ACCOUNT_ID","symbol":"600519.SH","volume":100,"price":1500.0}
```

For JSONL `server`, one input line produces one output line. Request `id` is echoed.

## Safety Boundaries

- Local only: `server` reads stdin and writes stdout; it does not open a socket.
- No broker software download or auto-install.
- No credential storage.
- No order retry loop.
- `capabilities` marks order placement and cancel actions as dangerous, marks `download` as
  `downloads_data` since it writes into the local QMT cache, and marks `sector` as
  `mutates_local_data` since it creates/modifies local custom sector definitions.
- A-share order volume must be a positive multiple of 100.
- Order price must be positive.
- Private `xtdata` / `XtQuantTrader` method names are blocked.
- QMT account permissions, risk checks, and final execution remain controlled by QMT and the broker.

## Command Help

```powershell
qmtcli --help
qmtcli capabilities --help
qmtcli schema --help
qmtcli examples --help
qmtcli data-call --help
qmtcli download --help
qmtcli sector --help
qmtcli fields --help
qmtcli trade-call --help
qmtcli watch --help
qmtcli rpc --help
qmtcli server --help
qmtcli mcp --help
```

## Development

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv build
```

Regenerate the static `fields` catalog from the doc appendix, and check the alignment matrices for
drift against the live doc pages (also runs on a weekly schedule in CI, see
[`.github/workflows/doc-drift.yml`](.github/workflows/doc-drift.yml)):

```powershell
python scripts/extract_doc_fields.py
python scripts/check_doc_drift.py
```

For coding agents, see [`AGENTS.md`](AGENTS.md).

PyPI packaging metadata is present so the name/build shape is reserved for future publishing, but
this project is not published by this repository workflow.
