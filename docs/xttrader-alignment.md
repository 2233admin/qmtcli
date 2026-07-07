# xttrader Alignment Matrix

Source: [https://dict.thinktrader.net/nativeApi/xttrader.html](https://dict.thinktrader.net/nativeApi/xttrader.html)

Checked: 2026-07-07, against `xtquant` 250516.1.1.

This table maps every function documented on the xttrader doc page to its `qmtcli` CLI surface.
Where a function is not exposed as a named command, it can still be called through the generic
`trade-call` (read/query or mutating) escape hatch, at the caller's own risk — no argument
validation beyond blocking private (`_`-prefixed) method names.

| XtQuantTrader function | doc section (Chinese) | CLI command | notes |
| --- | --- | --- | --- |
| `XtQuantTrader`, `register_callback`, `start`, `connect`, `stop`, `run_forever`, `set_relaxed_response_order_enabled` | 创建API实例 / 注册回调类 / 准备API环境 / 创建连接 / 停止运行 / 阻塞当前线程进入等待状态 / 开启主动请求接口的专用线程 | not exposed | internal gateway lifecycle; `QMTGateway.connect()` creates the `XtQuantTrader` instance and calls `start()`/`connect()` itself, once per CLI invocation |
| `subscribe`, `unsubscribe` | 订阅账号信息 / 反订阅账号信息 | internal, auto on connect | `QMTGateway.connect()` calls `trader.subscribe(account)` automatically whenever an account id is present (skipped for the account-less queries below); not a standalone command |
| `order_stock` | 股票同步报单 | `buy` / `sell` | fixed-price A-share orders |
| `order_stock_async`, `cancel_order_stock_async`, `cancel_order_stock_sysid`, `cancel_order_stock_sysid_async` | 股票异步报单 / 股票异步撤单 / 股票同步撤单（按 sysid） / 股票异步撤单（按 sysid） | `trade-call` | escape hatch only; the async variants are unsuitable for a one-shot CLI process, and the sysid-keyed cancel is an alternate identifier scheme not wired to the named `cancel` command |
| `cancel_order_stock` | 股票同步撤单 | `cancel` | |
| `fund_transfer`, `sync_transaction_from_external`, `smt_negotiate_order_async` | 资金划拨 / 外部交易数据录入 / 库存券约券申请 | `trade-call` | mutating; at the caller's own risk, no extra validation beyond blocking `_`-prefixed names |
| `query_stock_asset` | 资产查询 | `asset` | |
| `query_stock_orders` | 委托查询 | `orders` (`--cancelable-only`) | `cancelable_only` defaults to false, matching the SDK default |
| `query_stock_trades` | 成交查询 | `trades` | |
| `query_stock_positions` | 持仓查询 | `positions` | |
| `query_position_statistics` | 期货持仓统计查询 | `position-statistics` | |
| `query_credit_detail` | 信用资产查询 | `credit-detail` | |
| `query_stk_compacts` | 负债合约查询 | `stk-compacts` | |
| `query_credit_subjects` | 融资融券标的查询 | `credit-subjects` | |
| `query_credit_slo_code` | 可融券数据查询 | `credit-slo-code` | |
| `query_credit_assure` | 标的担保品查询 | `credit-assure` | |
| `query_new_purchase_limit` | 新股申购额度查询 | `ipo-limit` | |
| `query_ipo_data` | 当日新股信息查询 | `ipo-data` | connects to QMT session; no account id needed — the method itself takes no account argument |
| `query_account_infos` | 账号信息查询 | `account-infos` | connects to QMT session; no account id needed — the method itself takes no account argument |
| `query_account_status` | 账号状态查询 | `account-status` | connects to QMT session; no account id needed — the method itself takes no account argument |
| `query_com_fund` | 普通柜台资金查询 | `com-fund` | |
| `query_com_position` | 普通柜台持仓查询 | `com-position` | |
| `export_data`, `query_data` | 通用数据导出 / 通用数据查询 | `trade-call` | generic export/query surface; not individually wired to a named command |
| `smt_query_quoter`, `smt_query_compact` | 券源行情查询 / 约券合约查询 | `trade-call` | read-only securities-lending (约券) queries; documented on the doc page but not independently wired to a named command in this wave |
| `on_disconnected`, `on_account_status`, `on_stock_order`, `on_stock_trade`, `on_order_error`, `on_cancel_error`, `on_order_stock_async_response`, `on_smt_appointment_async_response` | 连接状态回调 / 账号状态信息推送 / 委托信息推送 / 成交信息推送 / 下单失败信息推送 / 撤单失败信息推送 / 异步下单回报推送 / 约券相关异步接口的回报推送 | not exposed | trader push callbacks delivered through `register_callback`; server mode's streaming support (`subscribe`/`subscribe_whole`/`unsubscribe`) covers `xtdata` quote subscriptions only, not these `XtQuantTrader` callbacks |

## Account-optional connect

`ipo-data`, `account-infos`, and `account-status` wrap `XtQuantTrader` methods that take no account
argument at all. `--account` is optional for these three: `qmtcli` still connects a QMT session
(`XtQuantTrader(path, session_id=...)` + `start()` + `connect()`), but skips `trader.subscribe(account)`
since there is no account to subscribe. Every other trader command in this table still requires
`--account`.
