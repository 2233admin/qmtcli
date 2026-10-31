# 常驻账户会话、全貌与增量

`qmtcli server` 为同一 `path/account/account_type` 保留一个 SDK 会话。连续查询复用
启动、握手和账户订阅，每次仍调用 SDK 查询最新结果，不返回本地缓存。
切换账户、路径、账户类型或账户订阅模式会关闭前一个会话；进程 EOF 也释放连接。
连接断开或账户查询报错后，不重放该请求；后续请求重新建连。

## 一次取账户全貌

```powershell
qmtcli --path D:\QMT\userdata_mini --account YOUR_ACCOUNT account-snapshot
```

RPC / JSONL：

```json
{"id":"snapshot-1","command":"account_snapshot","account":"YOUR_ACCOUNT"}
```

成功响应 `data` 包含 `asset`、`positions`、`orders`、`trades` 和 `meta`。
一次请求、一个连接、四次顺序 SDK 查询；不是柜台提供的原子快照。
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
{"id":2,"command":"account_snapshot","account":"YOUR_ACCOUNT"}
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

这只将资产部分交给已有、版本锁定的 MiniQMT 原生读取器；其他三项仍用 SDK，
仍需在兼容 SDK 的 Python 中运行 server。原生资产当前每次使用隔离子进程，尚未
改成常驻原生 worker，不能把 SDK 会话复用收益套到它上面。

Agent 自身可运行 Python 3.14、Rust 或其他语言，通过 stdin/stdout 驱动一个兼容
SDK 的 server 进程。无需将 SDK 导入 Agent 进程，也无需增加 TCP 服务。
单独的 `asset --backend native` 已有 Python 3.14 路径；完整账户原生查询尚未实现。

`account-snapshot` 可通过 CLI、RPC、server 和 MCP 发现；账户增量命令仅供 JSONL server。
MCP 的单次 snapshot 在内部复用一次连接，当前不跨 MCP 工具调用保留会话。

## 已验证与限制

离线真实 JSONL 调度基线：40 次查询从 40 次建连降到 1 次，仍执行 40 次查询。
实际 gateway + 假 SDK 测试同时验证一次注册、start、connect、subscribe 和一次 stop，
以及断线世代、失败清理、账户隔离和迟到回调。连接数降低不等于已测得相同比例的耗时加速。
当前客户端真实 SDK 只读检查及其限制记录在 OpenSpec 验证凭据中，不把模拟事件写成实盘验证。
2026-11-01 的两次只读检查收到了资产、持仓和委托回复，成交查询均未在预算内返回；
因此尚未取得完整四项成功样本。缺失成交回复会明确报错，不用空列表代替。
