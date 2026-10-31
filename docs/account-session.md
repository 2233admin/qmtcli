# 常驻账户会话、全貌与增量

`qmtcli server` 为同一 `path/account/account_type` 保留一个 SDK 会话。连续查询复用
启动、握手和账户订阅，每次仍调用 SDK 查询最新结果，不返回本地缓存。
切换账户、路径、账户类型或账户订阅模式会关闭前一个会话；进程 EOF 也释放连接。
连接断开或账户查询报错后，不重放该请求；后续请求重新建连。

## 一次取账户全貌

```powershell
qmtcli --path D:\QMT\userdata_mini --account YOUR_ACCOUNT account-snapshot
```

当前已验证的 MiniQMT 若遇到 SDK 成交查询无回复，显式选用原生成交：

```powershell
qmtcli --path D:\QMT\userdata_mini --account YOUR_ACCOUNT account-snapshot --trades-backend native
```

RPC / JSONL：

```json
{"id":"snapshot-1","command":"account_snapshot","account":"YOUR_ACCOUNT"}
```

成功响应 `data` 包含 `asset`、`positions`、`orders`、`trades` 和 `meta`。
SDK 后端使用一次请求、一个连接、四次顺序查询；原生后端使用独立连接。不是柜台提供的原子快照。
`meta.atomic=false`，同时给出 `started_at/finished_at/duration_ms`、`generation` 和
`sequence_start/sequence_end`。查询异常、缺失结果或收集期间断线会返回错误；合法空列表保留为空。
`duration_ms` 是四项收集时长，不包括此前建连耗时。
`timeout` 默认为5秒（0.1–60）；四项共享一个回复等待预算。SDK部分使用官方异步
查询接口配合限时等待，避免同步 `Future.result()` 无限等回复。它不是 SDK 建连、
原生函数调用或清理阶段的进程级硬超时；调用方仍应为 server 进程设置自己的期限。

## 订阅账户增量

启动 server 后保持 stdin 开着，先订阅，再取全貌：

```jsonl
{"id":1,"command":"account_subscribe","account":"YOUR_ACCOUNT"}
{"id":2,"command":"account_snapshot","account":"YOUR_ACCOUNT","trades_backend":"native"}
{"id":3,"command":"account_unsubscribe"}
```

SDK 推送会以独立 JSONL 行交错在响应之间：

```json
{"event":"account_update","type":"position","account":"YOUR_ACCOUNT","account_type":"STOCK","generation":2,"sequence":1,"data":{"stock_code":"600000.SH","volume":100}}
```

事件类型为 `asset/position/order/trade/status/order_error/cancel_error/disconnected`。
`data` 是原 SDK 对象的 JSON 表示，不把回报伪造为本地资金计算结果，也不自动去重。
序号表示收到回调的先后，不是交易所事件时间。

收到 `disconnected` 后停止依赖旧状态。后续查询重连时，同账户的本地订阅偏好保留，
新世代会发 `resync_required`，应重新查询全貌。旧世代迟到回调被抑制。
快照期间可能有事件，应按 generation/sequence 保存边界并按业务身份核对；本工具
没有建立一个保证与柜台完全一致的增量持仓缓存。没有真实事件也不会制造推送或轮询补推。

`account_unsubscribe` 关闭 JSONL 账户事件转发，保留查询连接和 SDK 账户订阅。
切到另一个账户会结束前一个账户的事件转发。此版本只维持一个活动账户，不维护无界连接池。
行情订阅继续使用已有 `subscribe/subscribe_whole/unsubscribe`，与账户事件分开。

## 原生接入与 Python 版本

```json
{"command":"account_snapshot","account":"YOUR_ACCOUNT","asset_backend":"native","timeout":5}
```

`asset_backend=native` 选择原生资产；`trades_backend=native` 选择原生成交，两者都选时
共用同一个隔离原生 worker 和本地会话。此分段选择模式的持仓、委托仍用 SDK，server
需运行在兼容 SDK 的 Python 中。完整原生模式见下节；单独的原生成交也不需要 SDK：

```powershell
qmtcli --path D:\QMT\userdata_mini --account YOUR_ACCOUNT trades --backend native
```

原生成交会先读取同一请求账户的资产，验证账户存在，再读取成交；552字节的成交记录
按实际分片重组。只有匹配版本服务的明确空列表结束回复，且账户验证成功，才返回空列表。
超时、账户错误、残缺分片和未知版本会报错，不用空列表掩盖失败。
数字 `order_id` 可能为0，不能据此把所有成交关联到同一委托。核对委托时使用账户、
证券和柜台 `order_sysid`；区分成交还需 `traded_id`，不自行补造缺失编号。
新增服务指纹检查包括 `OrderService_mini.dll`。

Agent 自身可运行 Python 3.14、Rust 或其他语言，通过 stdin/stdout 驱动一个兼容
SDK 的 server 进程。无需将 SDK 导入 Agent 进程，也无需增加 TCP 服务。
`asset --backend native` 和 `trades --backend native` 已在 Python 3.14 验证；
持仓、委托和完整快照现也支持原生查询，见下节。

`account-snapshot` 可通过 CLI、RPC、server 和 MCP 发现；账户增量命令仅供 JSONL server。
MCP 的单次 snapshot 在内部复用一次连接，当前不跨 MCP 工具调用保留会话。

## 已验证与限制

离线真实 JSONL 调度基线：40 次查询从 40 次建连降到 1 次，仍执行 40 次查询。
实际 gateway + 假 SDK 测试同时验证一次注册、start、connect、subscribe 和一次 stop，
以及断线世代、失败清理、账户隔离和迟到回调。连接数降低不等于已测得相同比例的耗时加速。
当前客户端真实 SDK 只读检查及其限制记录在 OpenSpec 验证凭据中，不把模拟事件写成实盘验证。
2026-11-01 最初的 SDK-only 检查在成交查询上超时；原生读取随后收到实际非空成交，
推翻了“当前成交为空”的猜测。显式 `trades_backend=native` 的完整 JSONL server 流程
现已连续两次返回四项数据，并完成订阅、退订和 EOF 退出。两种资产后端组合均验证通过。
这不等于 SDK 成交回调本身已修复，也不等于真实成交/断线增量事件全部验收。
实际返回的成交还与 SDK 委托逐条核对了证券、方向、系统号及数量范围。


## 常驻原生连接

JSONL server 为同一账户保留一个原生 worker、一次握手和一对队列；SDK 仍保留自己的
连接。每个原生请求分配新的请求编号和线协议序号，重新查询；不会返回上次结果。
`meta.native_generation` 表示当前原生 worker 的世代。账户切换或 EOF 关闭所属 worker；
超时、错误回复和进程崩溃会关闭故障 worker，当前请求报错，后续请求可以重新建连，
不会自动重放失败请求。单次 CLI/RPC 和 MCP 调用结束后仍释放连接。

2026-11-01 实机由 Python 3.14 驱动兼容 SDK 的 JSONL server，连续十次四项快照均成功，
SDK 和原生世代各自保持不变；每次成交均与 SDK 委托关联核对。首个混合后端快照含
原生 worker 初始化，其余九次使用原生资产与成交、SDK 持仓与委托。时间仅代表本机、
本账户及当前版本的样本，详见 OpenSpec 凭据，不作为交易时段的延迟保证。

## 四项全部使用原生接口

```powershell
python -m qmtcli --path D:\QMT\userdata_mini --account YOUR_ACCOUNT account-snapshot --backend native
python -m qmtcli --path D:\QMT\userdata_mini --account YOUR_ACCOUNT positions --backend native
python -m qmtcli --path D:\QMT\userdata_mini --account YOUR_ACCOUNT orders --backend native --cancelable-only
```

```json
{"id":1,"command":"account_snapshot","backend":"native","path":"D:\\QMT\\userdata_mini","account":"YOUR_ACCOUNT","timeout":5}
```

`backend=native` 对快照的四项都生效，优先于 `asset_backend/trades_backend` 的分段选择。
先校验账户资产，再顺序读取持仓、委托、成交；同一 JSONL server 内复用一个原生 worker。
Python 3.14 实测通过，整个查询进程禁止导入 xtquant 时也能工作；仍依赖已核验客户端
随附的原生队列 DLL。默认 `backend=sdk` 和既有分段后端保持兼容。

返回规范公开字段，不增加 SDK 内部 `m_*` 别名，不推测补充字段。委托 `cancelable_only`
要求布尔值，原生路径直接发送服务端可撤过滤位，不根据客户端状态码重新猜测。
476 字节委托、328 字节持仓均校验账户、有限数值和数量；列表使用实际结束标志与严格分片。
仅在同一操作成功校验账户后接受服务的明确空列表回复；错误、残片、超时都不能变为空列表。

`meta` 标注四项后端及 `native_generation`。原生连接世代与 SDK 事件世代独立；完全
原生查询不订阅账户事件，此时 `generation/sequence_*` 的 SDK 事件游标为初始值。
若同一 server 另外开了 SDK 账户订阅，它们仍只是 SDK 回调游标，不是原生事件序号。
快照依然是顺序查询，`atomic=false`，不代表柜台原子状态。原生推送、真实断线恢复、
大 QMT 和其他客户端版本尚未由本次实现验收；MCP 仍按工具调用释放连接。
