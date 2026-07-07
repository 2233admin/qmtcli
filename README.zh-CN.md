# qmtcli

[![tests](https://github.com/2233admin/qmtcli/actions/workflows/test.yml/badge.svg)](https://github.com/2233admin/qmtcli/actions/workflows/test.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

[English](README.md) | 中文

面向 QMT / miniQMT 和 XtQuant SDK 的本地 JSON CLI。

`qmtcli` 是一个很小的本地桥接工具：一边连接已经登录的券商 QMT 客户端，一边给偏好
进程 I/O 的工具使用，比如 Agent、脚本、调度器、Notebook 或其他自动化程序。它通过稳定的
stdin/stdout JSON 协议提供环境诊断、行情查询、账户查询和带基础保护的股票委托命令。

![qmtcli local JSON bridge](docs/assets/qmtcli-hero.png)

`qmtcli` 不安装 QMT，不保存凭据，不绕过券商风控，也不启动网络服务。使用前需要先在本机
安装并登录 QMT。

## 快速演示

发现命令能力：

```powershell
qmtcli capabilities
qmtcli schema
qmtcli examples
```

执行一次 JSON 请求：

```powershell
Get-Content examples\status.json | qmtcli rpc
```

启动给 Agent 或脚本使用的 JSONL 循环：

```powershell
qmtcli server
```

成功响应：

```json
{"ok":true,"data":{}}
```

失败响应：

```json
{"ok":false,"error":"message"}
```

如果请求里带 `id`，响应会原样带回。

## 为什么需要

QMT 把 `xtquant` 放在券商客户端安装目录里。直接在交易机上写 Python 脚本时还算方便，
但对 Agent 或基于进程的自动化程序来说，直接 import SDK 并不稳定。`qmtcli` 把 QMT 集成
留在本机，只对外提供简单 JSON 合约：

- `capabilities`、`schema`、`examples` 用于能力发现；
- `rpc` 用于 stdin/stdout 单请求；
- `server` 用于逐行 JSON 请求；
- 对只读调用、escape hatch、下单、撤单做明确标记；
- 测试里 fake `xtquant`，CI 不需要真实券商环境。

只要一个运行时能启动本地进程并交换 JSON，就能使用它。

## 功能

- 自动发现常见 Windows QMT SDK 路径；优先使用已安装在当前环境（venv/pip）的 `xtquant`，而不是
  QMT 自带的那份（见[安装](#安装)）。
- `status` 和 `doctor` 环境诊断，包含 SDK 来源（`environment` / `qmt_bundled` / `missing`）、
  `xtquant` 版本号、xtdc 可用性。
- 行情命令：交易日历、交易日期、板块、tick、K 线、L2 数据、合约/ETF/可转债/新股/指数权重元数据、
  财务数据。
- `fields`：从文档附录提取的静态 xtdata 字段名参考字典（tick、kline、balance 等），完全离线，
  不需要 QMT 环境。
- 感知 pandas 的 JSON 输出：xtdata 返回的 DataFrame/Series 会序列化成逐行记录（时间索引会保留成
  普通列），NaN/NaT/`pd.NA`/numpy 标量都会转成合法的 JSON 值，而不是非法的 `NaN` token 或读不懂的
  对象转储。
- `download` 命令用于把数据下载进本地 QMT 缓存（历史行情、财务数据、板块、指数权重、可转债、
  ETF 信息、节假日、合约信息）。
- 账户查询：资产、持仓、委托（支持 `--cancelable-only`）、成交。
- 交易查询命令：持仓统计、信用/融资融券查询、新股额度与数据、账号信息/状态、普通柜台资金/持仓
  查询——见[交易查询命令](#交易查询命令)。
- 固定价 A 股 `buy`、`sell`、`cancel`。
- `data-call` 调用公开的 `xtquant.xtdata` 方法。
- `trade-call` 调用公开的 `XtQuantTrader` 方法。
- 可选的独立 xtdatacenter（xtdc）数据模式，通过 `--xtdc-token` 开启（实验性）——见
  [独立数据模式](#独立数据模式xtdc实验性)。
- Agent / 脚本协议命令：`capabilities`、`schema`、`examples`、`rpc`、`server`。
- 定时运行的 `doc-drift` GitHub Action（每周一次，也支持手动触发）会对照官方文档页面重新核对下面
  的对齐矩阵，一旦文档新增的函数还没体现在矩阵里就自动开 issue；见 `scripts/check_doc_drift.py`。

完整的函数对命令覆盖矩阵（对照官方
[xtdata 文档](https://dict.thinktrader.net/nativeApi/xtdata.html)和
[xttrader 文档](https://dict.thinktrader.net/nativeApi/xttrader.html)）见
[`docs/xtdata-alignment.md`](docs/xtdata-alignment.md)和
[`docs/xttrader-alignment.md`](docs/xttrader-alignment.md)。

## 安装

推荐：用 `sdk` extra 安装，让 `xtquant`/`pandas`/`numpy` 来自当前环境而不是 QMT 自带的
`site-packages`；这样券商 QMT 客户端只需要提供本地交易/行情服务，不必再提供 Python SDK 本身：

```powershell
uv sync --extra dev --extra sdk
pip install -e ".[dev,sdk]"
```

不装 `sdk` extra 时的兜底方案仍然可用——找不到已安装的 SDK 时，`qmtcli` 会回退到 QMT 安装目录自带
的 `xtquant`/`numpy`/`pandas`——但自带版本可能比当前文档旧（比如部分自带版本缺少
`get_period_list`），而且绝不能让它自带的 `numpy` 盖过 venv 自己的 `numpy`。`qmtcli doctor` 会
报告最终生效的来源，字段是 `sdk_source`。详见
[Runtime caveats](docs/xtdata-alignment.md#runtime-caveats)（英文）。

本地开发：

```powershell
uv sync --extra dev
uv run qmtcli status
```

editable pip 安装：

```powershell
pip install -e .[dev]
qmtcli status
```

## Agent 和脚本用法

发现能力：

```powershell
qmtcli capabilities
qmtcli schema
qmtcli examples
```

单次 RPC：

```powershell
Get-Content examples\status.json | qmtcli rpc
Get-Content examples\data_call.json | qmtcli rpc
```

JSONL 循环：

```powershell
.\examples\jsonl_server.ps1
```

通用集成说明见 [`examples/agent_tool.md`](examples/agent_tool.md)。录制演示的脚本见
[`docs/demo_storyboard.md`](docs/demo_storyboard.md)。

所有行情命令（`calendar`、`bars`、`sector-stocks`、`download` 等）现在也能通过 `rpc`/`server`
调用，不再局限于 CLI；把对应的 CLI 参数名当 JSON 字段发送即可，例如
`{"command":"bars","symbols":["600519.SH"],"period":"1d"}`。命令名支持短横线或下划线两种写法
（`sector-stocks` 或 `sector_stocks`）。

## Server 流式推送

只有 `server` 模式支持 `subscribe`、`subscribe_whole`、`unsubscribe`，分别包装了回调式的
`xtdata.subscribe_quote`、`subscribe_whole_quote`、`unsubscribe_quote`：

```json
{"command":"subscribe","symbol":"600519.SH","period":"1d"}
{"command":"subscribe_whole","symbols":["600519.SH","000001.SZ"]}
{"command":"unsubscribe","seq":1}
```

订阅成功会返回 `{"ok":true,"data":{"seq":1}}`，此后 xtquant 每次推送行情都会单独打印一行 JSONL，
带 `event` 字段而不是 `ok`，和普通响应交替出现在同一个 stdout 流里：

```json
{"ok":true,"data":{"seq":1}}
{"event":"quote","seq":1,"symbol":"600519.SH","data":{"600519.SH":{"lastPrice":1500.0}}}
```

单次的 `rpc` 命令和 CLI 都会拒绝订阅命令，返回
`{"ok":false,"error":"subscribe commands require server mode"}`，因为订阅只有在 `server` 让进程
常驻时才有意义。

## QMT 路径

可以传 QMT 安装根目录，也可以传 `userdata_mini` 目录：

```powershell
qmtcli --path D:\DFZQxtqmt_client_real_win64 doctor
qmtcli --path D:\DFZQxtqmt_client_real_win64\userdata_mini --account ACCOUNT_ID asset
```

如果不传 `--path`，会检查这些默认路径：

- `D:\DFZQxtqmt_client_real_win64`
- `D:\DFZQxtqmt_client_test_win64`
- `C:\DFZQxtqmt_client_real_win64`
- `C:\DFZQxtqmt_client_test_win64`

预期 SDK 位置：

```text
<QMT root>\bin.x64\Lib\site-packages\xtquant
```

## 常用命令

诊断：

```powershell
qmtcli status
qmtcli doctor
python -m qmtcli status
```

行情：

```powershell
qmtcli calendar SH
qmtcli trading-dates SH --count 5
qmtcli sector-list
qmtcli sector-stocks 沪深A股
qmtcli full-tick 600519.SH 000001.SZ
qmtcli bars 600519.SH --period 1d --count 100
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

静态字段名参考字典（完全离线，不需要 QMT 环境）：

```powershell
qmtcli fields
qmtcli fields tick
qmtcli fields balance
```

L2 命令需要券商的 Level-2 行情权限，且不在官方 xtdata 文档页范围内：

```powershell
qmtcli l2-quote 600519.SH
qmtcli l2-order 600519.SH
qmtcli l2-transaction 600519.SH
```

把数据下载进本地 QMT 缓存；这些命令在 SDK 下载完成后返回，本身不会打印行情数据——
行情数据请用上面的读取命令：

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

账户和交易命令需要 `--account`：

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

## 交易查询命令

这些命令包装了具名的 `XtQuantTrader` 查询方法；完整映射见
[`docs/xttrader-alignment.md`](docs/xttrader-alignment.md)（英文）。大部分需要 `--account`：

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

`ipo-data`、`account-infos`、`account-status` 包装的 `XtQuantTrader` 方法本身不带账户参数，所以这
三个命令的 `--account` 是可选的——`qmtcli` 仍会连接 QMT 会话，只是跳过订阅账户：

```powershell
qmtcli ipo-data
qmtcli account-infos
qmtcli account-status
```

## Escape Hatches

`data-call` 调用公开的 `xtquant.xtdata` 方法：

```powershell
qmtcli data-call get_stock_list_in_sector --args "[\"沪深A股\"]"
qmtcli data-call get_cb_info --args "[\"123001.SZ\"]"
```

`trade-call` 在连接账户后调用公开的 `XtQuantTrader` 方法。默认会把 `StockAccount` 对象
放在位置参数最前面：

```powershell
qmtcli --account ACCOUNT_ID trade-call query_stock_orders
qmtcli --account ACCOUNT_ID trade-call some_method --args "[1,2]" --kwargs "{\"flag\":true}"
qmtcli --account ACCOUNT_ID trade-call method_without_account --no-account
```

`_` 开头的私有方法名会被阻止。

## 独立数据模式（xtdc，实验性）

`--xtdc-token`（或环境变量 `QMTCLI_XTDC_TOKEN`）会开启独立 xtdatacenter 数据模式：在执行任何命令
之前，`qmtcli` 会先调用 `xtquant.xtdatacenter.set_token()` 和 `.init()`，这样 `xtdata` 调用就能走
迅投投研的独立数据服务，而不必依赖本地 QMT 客户端：

```powershell
$env:QMTCLI_XTDC_TOKEN = "YOUR_TOKEN"
qmtcli calendar SH

qmtcli --xtdc-token YOUR_TOKEN --xtdc-port 58620 calendar SH
```

这需要有效的迅投投研数据 token，且目前是**实验性**功能——只验证到 `init()` 调用成功，还没有走通
端到端的真实数据链路。`--xtdc-port`（默认 `58620`）已经接入命令行，但还没有对接到具体的
xtdatacenter 调用上。`qmtcli doctor` 会用 `xtdc_available` 字段报告 `xtquant.xtdatacenter` 模块本身
是否可导入。详见 [Runtime caveats](docs/xtdata-alignment.md#runtime-caveats)（英文）。

## JSON 请求示例

```json
{"command":"status"}
{"command":"data_call","method":"get_stock_list_in_sector","args":["沪深A股"]}
{"command":"buy","account":"ACCOUNT_ID","symbol":"600519.SH","volume":100,"price":1500.0}
```

`server` 模式下一行输入对应一行输出。请求里的 `id` 会被带回。

## 安全边界

- 本地使用：`server` 只读 stdin、写 stdout，不打开 socket。
- 不下载或自动安装券商软件。
- 不保存账号密码或登录凭据。
- 不自动重试下单。
- `capabilities` 会标记下单和撤单能力为危险动作；`download` 因为写入本地 QMT 缓存，被标记为
  `downloads_data`。
- A 股委托数量必须是正的 100 倍数。
- 委托价格必须大于 0。
- 阻止调用 `_` 开头的 `xtdata` / `XtQuantTrader` 方法。
- 账户权限、风控检查和最终成交仍由 QMT 和券商控制。

## 命令帮助

```powershell
qmtcli --help
qmtcli capabilities --help
qmtcli schema --help
qmtcli examples --help
qmtcli data-call --help
qmtcli download --help
qmtcli fields --help
qmtcli trade-call --help
qmtcli rpc --help
qmtcli server --help
```

## 开发

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv build
```

从文档附录重新生成静态 `fields` 字典，并检查对齐矩阵是否和官方文档产生了漂移（CI 里每周也会自动
跑一次，见 [`.github/workflows/doc-drift.yml`](.github/workflows/doc-drift.yml)）：

```powershell
python scripts/extract_doc_fields.py
python scripts/check_doc_drift.py
```

给代码 Agent 的项目说明见 [`AGENTS.md`](AGENTS.md)。

当前仓库保留了 PyPI 打包元数据，但不在当前工作流中发布。
