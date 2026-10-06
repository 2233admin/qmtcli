# qmtcli

A local JSON bridge that lets agents read QMT market and account data and place guarded stock orders.

## Language

**QMT**:
The broker-distributed XunTou (迅投) trading client installed on the user's machine. qmtcli connects to it and never installs, downloads, or vendors it.
_Avoid_: platform, server

**miniQMT**:
The QMT mode that exposes the `xtquant` API to external programs; its `userdata_mini` directory is what `--path` / `path` points at.
_Avoid_: mini client, QMT lite

**XtQuant SDK**:
The `xtquant` Python package bundled with QMT, made of `xtdata` (market and reference data) and `xttrader` (`XtQuantTrader`, account and order operations).
_Avoid_: QMT API, broker SDK

**Session**:
One `XtQuantTrader` connection to the running QMT client, identified by a session id. Some trade queries need only a session, not an account.
_Avoid_: login, connection pool

**Account**:
The QMT account id passed as `--account` / `account`, with `account_type` defaulting to `STOCK`, wrapped as an `xtquant` `StockAccount` for trade calls.
_Avoid_: user, login

**Asset**:
The cash and valuation summary of an account, returned by `asset`.
_Avoid_: balance, portfolio

**Position**:
A holding of one symbol in an account, returned by `positions`.
_Avoid_: holding, lot

**Order**:
A fixed-price stock buy or sell instruction submitted with `buy` / `sell` and cancelled with `cancel` by QMT order id. Its price must be positive and its volume a positive multiple of 100.
_Avoid_: trade (a trade is a fill)

**Trade**:
A fill of an order, returned by `trades`.
_Avoid_: order, execution report

**Guarded trading**:
Order placement and cancellation through the named `buy`, `sell`, and `cancel` commands, which validate their inputs. MCP mode excludes them by design.
_Avoid_: safe trading, auto-trading

**Escape hatch**:
`data-call` and `trade-call`, which call any public `xtdata` or `XtQuantTrader` method by name; `_`-prefixed methods are blocked, and `trade-call` is not guarded.
_Avoid_: raw mode, passthrough

**Danger level**:
The `danger` field of each capability: `safe`, `downloads_data`, `mutates_local_data`, `escape_hatch`, `places_order`, or `cancels_order`.
_Avoid_: risk level, permission

**Capability**:
One entry of `AGENT_CAPABILITIES` in `cli.py`, the single registry that `capabilities`, `schema`, and the MCP tool list are generated from.
_Avoid_: tool, endpoint

**Agent protocol**:
The `qmtcli.agent.v1` request and response contract: a request names a `command`, a response is `{"ok": true, "data": ...}` or `{"ok": false, "error": "..."}`, and a request `id` is echoed.
_Avoid_: API, REST

**RPC mode**:
`qmtcli rpc`: one JSON request on stdin, one JSON response on stdout.
_Avoid_: request mode

**Server mode**:
`qmtcli server`: one JSON request per stdin line and one JSON response per stdout line, with subscription pushes as `event` lines. It has no network listener.
_Avoid_: daemon, HTTP server

**MCP mode**:
`qmtcli mcp`: a stdio MCP server whose tools are generated from the capability list and dispatched through the same RPC handler.
_Avoid_: plugin, second registry

**xtdc mode**:
The experimental standalone `xtquant.xtdatacenter` data mode enabled by `--xtdc-token` or `QMTCLI_XTDC_TOKEN`.
_Avoid_: cloud mode
