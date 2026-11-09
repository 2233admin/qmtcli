# Rust QMTCLI：双核心 workspace

当前版本 0.3.0：新增大 QMT 公开数据读取；行情及账户查询可通过 CLI/RPC/JSONL 调用，支持常驻会话。
账户 IPC 和隔离 DLL worker 已实现并通过自有合成服务验证；真实账户接入尚待验收。
尚不能完整替代 Python QMTCLI 或 xtquant。

```text
qmtcli-rs（统一 agent 入口）
 ├─ qmt-quote：版本校验、TCP/BSON/CRC、心跳、保留行情会话
 └─ qmt-trade：账户 IPC、回包关联/分片、四项查询 → 同一 exe 的隔离 DLL worker
```

两个核心互不依赖。旧 `experiments/native-quote-rs` 只保留 CLI/benchmark
适配器，依赖同一份 qmt-quote；没有第二份行情协议实现。Cargo.lock 在仓库根。
Python 入口保留，可作为对照和回退。MCP、批量历史下载、订阅和竞价专用数据暂不在 Rust 能力中。

## 大 QMT 公开数据读取

使用已安装客户端的正常公式 RPC（`qmt_api` 同一路径），无 Python/xtquant
运行时依赖。启动大 QMT 并正常登录后，将安装根目录传入 `path`；首版匹配
已验收的 FormulaLib/net 文件指纹，其他版本会返回明确错误。

```powershell
Get-Content -Encoding UTF8 .\examples\rust-big-qmt-public.jsonl | .\dist\rust\qmtcli-rs.exe server
```

或启动一次 `qmtcli-rs.exe server`，逐行发送：

```json
{"id":1,"command":"instrument-detail","backend":"formula","path":"D:\\DFZQxtqmt_client_real_win64","symbols":["000001.SZ"]}
{"id":2,"command":"daily-bars","backend":"formula","path":"D:\\DFZQxtqmt_client_real_win64","symbols":["000001.SZ","600000.SH"],"count":2}
{"id":3,"command":"full-tick","backend":"formula","path":"D:\\DFZQxtqmt_client_real_win64","symbols":["000001.SZ","600000.SH"]}
```

`instrument-detail` 一次一个代码，返回证券资料的原始字段；`daily-bars` 返回
最近 count 个日线的 open/high/low/close/volume/amount，未复权，count 默认 2、
范围 1–1000；`full-tick` 返回每个代码的一个缓存快照，保留盘口等原始数值字段。
成交量/金额单位沿用客户端字段，不做单位换算。代码仅接受 CODE.SH/SZ/BJ，
最多 100 个且不重复；并非所有代码都有数据。时间区间、自选字段、其他周期和
下载参数尚未实现，传入会报错，避免忽略参数后返回错误范围的数据。

成功包的 `data` 为 `{meta, data}`：meta 包含 `source:"client-cache"`、
`realtime:false`、`freshness:"unknown"` 和 `retrieved_at_unix_ms`（本机取回时间）；
行情 `data` 按代码映射到 `[{time,fields}]`。`time` 是服务返回的数据时间，
日线为 YYYYMMDD，快照为 YYYYMMDD HH:MM:SS。取回时间不代表行情更新时间。
当前客户端实测日线最新 20260803、快照 20260521，不能当作今日实时数据。
合法空缓存返回空数组；错误、缺失证券或部分回报不会伪造成成功数据。

默认读取安装目录 `config/formulaserver/formulaserver.ini` 的 `[server_formula]`
address 端口，连接目的地固定 127.0.0.1。`doctor` 配 `backend:formula` 可校验
文件及配置而不连接。`timeout` 默认 5 秒、范围 0.1–60 秒；单次网络操作使用
总期限，最大回复 4 MiB，仅支持已验证的明文 BSON 完整回复。压缩、流式回复、
未知帧和服务拒绝均报错并关闭连接。连续同 path/timeout 请求复用连接；
输入校验错误不丢弃健康连接，连接失败后下一条请求重连，不重放失败请求。
EOF 关闭本进程拥有的连接，不关闭 QMT。

实际入口验收可运行（脚本只发上述公开读取请求）：

```powershell
python .\experiments\accept_big_qmt_public.py --exe .\dist\rust\qmtcli-rs.exe --path D:\DFZQxtqmt_client_real_win64 --receipt .\dist\rust\big-qmt-public-acceptance.json
```

## 构建和启动

Windows x64，在仓库根目录执行：

```powershell
cargo +1.99.1-x86_64-pc-windows-gnu build --release --locked -p qmtcli-rs
.\target\release\qmtcli-rs.exe capabilities
.\target\release\qmtcli-rs.exe schema
.\target\release\qmtcli-rs.exe examples
.\target\release\qmtcli-rs.exe server
```

构建和执行都不需要 Python。运行要求匹配的已安装 QMT，服务已启动；
`backend:native` 是 MiniQMT 接入，`backend:formula` 是上述大 QMT 公开读取。
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
MiniQMT 业务请求必须显式 `backend:native`，不把 Python 的 SDK 默认值悄悄改成 native。
行情端口默认 58610，可指定 `quote_port`；`timeout` 为 0.1–60 秒，默认 5 秒。
doctor 可通过 RPC 指定 path，核验行情/账户文件指纹和账户队列是否存在，不建立服务连接。

成功为 `{"ok":true,"data":...}`，失败为 `{"ok":false,"error":"..."}`；非 null
请求 id 回显。RPC 查询失败退出码非零。server 对错误请求逐行报错后继续运行。
每个请求上限 1 MiB；超长行丢弃后继续处理下一行。stdout 只输出 JSON。

相同路径、端口和超时复用同一个 QuoteSession，每次仍发起新查询。改变配置会
关闭旧会话再连接。协议/查询失败丢弃会话，本次请求不自动重放；下一次请求可
建立新会话。输入校验失败保留健康会话。EOF 释放本进程拥有的 socket。
行情时间戳来自服务缓存，不代表实时推送。版本不匹配或服务不可用就报错。

账户请求示例（替换路径与账号）：

```json
{"id":2,"command":"account_snapshot","backend":"native","path":"D:\\QMT","account":"YOUR_ACCOUNT","account_type":"STOCK","timeout":5}
```

还可查询 `asset/positions/orders/trades`；`orders` 支持 `cancelable_only:true`。
只支持已核验的 Windows x64 普通股票账户。账户入口检查三个安装 DLL 的 SHA256，
只在私有 worker 中加载 ringbuffer.dll；没有 Python worker。账户/路径相同就复用 worker，
每次仍发新查询；切换账户重建。请求序号、session、记录长度和分片偏移均校验；
错误后关闭 worker，本次不重放，下一次请求重新连接。行情与账户的连接独立。

`account_snapshot` 顺序读取资产、持仓、委托、成交，`meta.atomic:false`。
`native_generation` 表示 worker 代次；`event_sequence_available:false`，
generation/sequence_start/sequence_end 的 0 不是有效事件游标。尚无原生账户推送。
不通过成交重新计算资产，不删除重复业务行。空列表必须有同次账户校验和明确结束回包。

父进程使用 Windows kill-on-close Job 管理 worker，EOF/超时关闭自己拥有的进程；
强制结束父进程也会终止 worker。供应商 C++ 对象、映射及模块由 worker 退出时回收，
不猜测析构 ABI。回复队列以随机会话号独占创建，仅尝试删除自己创建的文件；如果服务
仍持有映射，文件删除可能失败，不扫描或删除其他队列。账户 IPC 等待预算为 timeout，
首次文件指纹检查先于该预算，元数据 duration_ms 包含这部分时间。
worker 单条响应上限 16 MiB、列表最多 100000 行，超限报错。

在其他 Rust 程序直接使用 AccountSession 时，宿主必须分派同一 exe 的
`--internal-account-worker` 到 `qmt_trade::run_worker()`；qmtcli-rs 已完成此分派。
私有 worker 模式不是 agent 的公开调用契约。

## 当前交付边界

| 能力 | 状态 |
|---|---|
| CLI、RPC、JSONL、发现、行情 doctor/status | 已实现 |
| 行情快照、连接复用与心跳分流 | 已实现，入口回放通过；真实长连接仍待验收 |
| 四类账户记录解码 | 已实现，与既有 Python codec 的合成 fixture 对账 |
| Rust 账户 IPC、DLL ABI、隔离 worker、四项查询 | 已实现；实际安装 DLL + 自有合成服务通过，真实账户验收未完成 |
| 原生账户事件订阅、重连期间增量补齐 | 未完成，不在能力发现中标可用 |
| 大 QMT 公开证券资料、日线 OHLCV/金额、缓存快照 | 已实现，使用 formula 后端及独立协议配置 |
| 大 QMT 账户、MCP、批量历史下载、订阅、竞价专用数据 | 未完成 |

## 验证

MiniQMT 真实只读验收工具（开发验收使用 Python 和 psutil；Rust 运行不需要它们）：

```powershell
$env:QMTCLI_ACCOUNT = Read-Host 'MiniQMT account (not password)'
python .\experiments\accept_miniqmt.py --exe .\dist\rust\qmtcli-rs.exe --path D:\DFZQxtqmt_client_real_win64 --scope actual-miniqmt --snapshots 2 --idle-seconds 65 --receipt .\dist\rust\miniqmt-live.json
Remove-Item Env:\QMTCLI_ACCOUNT
```

需先正常启动、登录 MiniQMT。该工具不切换客户端、不修改登录配置。
无服务队列或未提供账户时记录 blocked；不把它记为验收成功。
账户仅从指定环境变量读取并通过 stdin 发送，不进入命令行或报告；报告仅记录
身份匹配标记、有限数检查、记录数、代次、公开行情时间及进程退出状态。
默认读取两次四项快照，再验证非法账户类型不会破坏会话、行情与账户会话独立、
空闲后可继续读取、EOF 关闭自己的 worker。`--snapshots` 支持 2–40 次，
`--idle-seconds` 支持 0–120 秒。合成服务必须标为 `--scope synthetic`。
这些检查不代表行情推送、账户事件、实际柜台断线恢复或完整 SDK 字段对账已完成。

```powershell
cargo +1.99.1-x86_64-pc-windows-gnu test --release --locked --workspace --all-targets
cargo +1.99.1-x86_64-pc-windows-gnu clippy --release --locked --workspace --all-targets -- -D warnings
cargo +1.99.1-x86_64-pc-windows-gnu fmt --all -- --check
```

自动测试不连接真实券商。账户 fixtures 为合成二进制及由既有 Python decoder
产生的完整预期字段；包含 Int64 数量、中文备注和零委托 id，无真实账户数据。
具体进度及实际运行回执仍归 `openspec/changes/account-session-stream/`。

本机 GNU dlltool 在 windows-sys 的导入库生成阶段曾停滞；已有 LLVM 的
llvm-dlltool 可完成相同构建。本机验证命令在进程内把含该工具的私有目录
`F:\projects\_research\qmt-ida-20261031\llvm-dlltool`（文件名 dlltool.exe）
与 `C:\Program Files\LLVM\bin` 前置 PATH；未修改全局工具链配置。
