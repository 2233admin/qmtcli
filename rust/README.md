# Rust QMTCLI：双核心 workspace

当前阶段：行情 CLI/RPC/JSONL 可运行；账户核心已迁入四类记录解码，账户传输和
隔离 DLL worker 尚未实现。不是完整替代 Python QMTCLI 或 xtquant。

```text
qmtcli-rs（统一 agent 入口）
 ├─ qmt-quote：版本校验、TCP/BSON/CRC、心跳、保留行情会话
 └─ qmt-trade：账户编码及资产/持仓/委托/成交记录解码
```

两个核心互不依赖。旧 `experiments/native-quote-rs` 只保留 CLI/benchmark
适配器，依赖同一份 qmt-quote；没有第二份行情协议实现。Cargo.lock 在仓库根。
Python 入口保留，可作为对照和回退。MCP、历史、订阅和竞价暂不在 Rust 能力中。

## 构建和启动

Windows x64，在仓库根目录执行：

```powershell
cargo +1.99.1-x86_64-pc-windows-gnu build --release --locked -p qmtcli-rs
.\target\release\qmtcli-rs.exe capabilities
.\target\release\qmtcli-rs.exe schema
.\target\release\qmtcli-rs.exe examples
.\target\release\qmtcli-rs.exe server
```

构建和执行都不需要 Python。行情运行仍要求匹配的已安装 MiniQMT，服务已启动。
`capabilities/schema/examples/status` 不要求 QMT 存在，也不会加载账户 DLL。
status 的连接字段表示当前进程拥有的会话，不证明柜台登录或实时行情可用。

## agent 输入输出

server 每行接收一个 JSON 请求，每行输出一个结果；短调用可使用
`qmtcli-rs rpc '<JSON>'` 或把一个 JSON 对象送入 `qmtcli-rs rpc` 的 stdin。
复用连接应启动一次 server，持续交换 JSONL，最后关闭 stdin。

```json
{"id":1,"command":"full_tick","backend":"native","path":"D:\\QMT","symbols":["600000.SH","000001.SZ"]}
```

把 path 改为真实 QMT 安装根目录或 userdata_mini。full_tick/full-tick 都接受。
业务请求必须显式 `backend:native`，不把 Python 的 SDK 默认值悄悄改成 native。
行情端口默认 58610，可指定 `quote_port`；`timeout` 为 0.1–60 秒，默认 5 秒。
doctor 可通过 RPC 指定 path，仅核验行情文件指纹，不建立服务连接。

成功为 `{"ok":true,"data":...}`，失败为 `{"ok":false,"error":"..."}`；非 null
请求 id 回显。RPC 查询失败退出码非零。server 对错误请求逐行报错后继续运行。
每个请求上限 1 MiB；超长行丢弃后继续处理下一行。stdout 只输出 JSON。

相同路径、端口和超时复用同一个 QuoteSession，每次仍发起新查询。改变配置会
关闭旧会话再连接。协议/查询失败丢弃会话，本次请求不自动重放；下一次请求可
建立新会话。输入校验失败保留健康会话。EOF 释放本进程拥有的 socket。
行情时间戳来自服务缓存，不代表实时推送。版本不匹配或服务不可用就报错。

## 当前交付边界

| 能力 | 状态 |
|---|---|
| CLI、RPC、JSONL、发现、行情 doctor/status | 已实现 |
| 行情快照、连接复用与心跳分流 | 已实现，入口回放通过；真实长连接仍待验收 |
| 四类账户记录解码 | 已实现，与既有 Python codec 的合成 fixture 对账 |
| Rust 账户 IPC、DLL ABI、隔离 worker、四项查询 | 未实现，不在命令发现中标可用 |
| 大 QMT、MCP、历史、订阅、竞价 | 未完成 |

## 验证

```powershell
cargo +1.99.1-x86_64-pc-windows-gnu test --release --locked --workspace --all-targets
cargo +1.99.1-x86_64-pc-windows-gnu clippy --release --locked --workspace --all-targets -- -D warnings
cargo +1.99.1-x86_64-pc-windows-gnu fmt --all -- --check
```

自动测试不连接真实券商。账户 fixtures 为合成二进制及由既有 Python decoder
产生的完整预期字段；包含 Int64 数量、中文备注和零委托 id，无真实账户数据。
具体进度及实际运行回执仍归 `openspec/changes/account-session-stream/`。
