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

- 自动发现常见 Windows QMT SDK 路径。
- `status` 和 `doctor` 环境诊断。
- 行情命令：交易日历、交易日期、板块、tick、K 线、L2 数据、合约/ETF/可转债/新股/指数权重元数据、
  财务数据。
- `download` 命令用于把数据下载进本地 QMT 缓存（历史行情、财务数据、板块、指数权重、可转债、
  ETF 信息、节假日、合约信息）。
- 账户查询：资产、持仓、委托、成交。
- 固定价 A 股 `buy`、`sell`、`cancel`。
- `data-call` 调用公开的 `xtquant.xtdata` 方法。
- `trade-call` 调用公开的 `XtQuantTrader` 方法。
- Agent / 脚本协议命令：`capabilities`、`schema`、`examples`、`rpc`、`server`。

完整的函数对命令覆盖矩阵（对照官方
[xtdata 文档](https://dict.thinktrader.net/nativeApi/xtdata.html)）见
[`docs/xtdata-alignment.md`](docs/xtdata-alignment.md)。

## 安装

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
qmtcli --account ACCOUNT_ID trades
qmtcli --account ACCOUNT_ID buy 600519.SH 100 1500.00
qmtcli --account ACCOUNT_ID sell 600519.SH 100 1500.00
qmtcli --account ACCOUNT_ID cancel ORDER_ID
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

给代码 Agent 的项目说明见 [`AGENTS.md`](AGENTS.md)。

当前仓库保留了 PyPI 打包元数据，但不在当前工作流中发布。
