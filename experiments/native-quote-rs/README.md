# Rust 原生行情请求实验适配器

2026-11-02：行情实现和测试已迁到 `rust/qmt-quote`。本目录保留旧实验 exe 与
benchmark 入口供已有研究脚本使用，二者都调用同一份核心。正式 Rust 入口和
当前能力见 [Rust workspace](../../rust/README.md)。根目录 Cargo.lock 为唯一锁文件。

旧研究驱动若硬编码本目录的 target 路径，构建时显式指定 --target-dir experiments/native-quote-rs/target。

问题：能否沿用官方 `get_full_tick(code_list)` 的业务接口，由 Rust 直接请求
MiniQMT，脱离 Python 和 xtquant 的运行时依赖？本目录用于验证这件事，尚未接入
QMTCLI 的正式后端，不是官方 Rust SDK。

在本工作树根目录执行：

```powershell
cargo run --locked --manifest-path experiments/native-quote-rs/Cargo.toml -- D:\DFZQxtqmt_client_real_win64 600000.SH 000001.SZ
```

编译后也可独立运行，不需要启动 Python：

```powershell
.\target\debug\qmt-native-quote-experiment.exe D:\DFZQxtqmt_client_real_win64 600000.SH 000001.SZ
```

程序输出 `{"ok":true,"data":{"600000.SH":{...},"000001.SZ":{...}}}`。
错误输出 `{"ok":false,"error":"..."}` 并以退出码 1 结束。
路径也可指向安装目录下的 `userdata_mini`。

Rust 库调用方式：

```rust,no_run
use qmt_quote::{QuoteClient, Result};

fn main() -> Result<()> {
    let client = QuoteClient::new(r"D:\DFZQxtqmt_client_real_win64");
    let ticks = client.get_full_tick(&["600000.SH", "000001.SZ"])?;
    println!("{ticks:?}");
    Ok(())
}
```

需要复用连接时，显式创建会话：

```rust,no_run
let client = QuoteClient::new(r"D:\DFZQxtqmt_client_real_win64");
let mut session = client.connect()?;
let first = session.get_full_tick(&["600000.SH", "000001.SZ"])?;
let second = session.get_full_tick(&["600000.SH", "000001.SZ"])?;
```

`connect` 校验版本并认证一次；每次读取仍发送新请求，使用新序列号和独立超时预算，
不缓存快照。已识别的 `kind=1` 心跳先校验长度、标志、CRC 和零填充，再继续读取
本次 RPC 回包；心跳序列不会拿来匹配查询序列。未知或损坏报文仍报错。
连接出错、超时或返回数据异常时，会话关闭，后续读取明确报 `session closed`。
需要重新连接时再次调用 `client.connect()`；没有自动重试或重放。
代码输入校验失败不会关闭仍健康的连接。会话由单个可变 Rust 所有者使用，释放时关闭。

返回 `bson::Document`，保留官方“代码 → 字段”的映射、Int64 时间戳和深度数组。
`code_list` 也接受官方规定的市场代码，例如 `client.get_full_tick(&["SH", "SZ"])?`；
市场查询允许返回相应市场下的证券代码，仍拒绝无关市场的返回。
使用标准库 TCP，BSON 编解码复用 MongoDB 的 `bson` 库，zlib/CRC/SHA256
复用 `flate2`、`crc32fast`、`sha2`。`Cargo.lock` 固定完整依赖。
不会加载安装目录中的 DLL；读取五个二进制文件仅用于 SHA256 版本核验。

MiniQMT 必须已经运行。目标固定为 `127.0.0.1`，端口默认 58610，Rust 库可用
`with_port` 指定已有端口。`with_timeout` 设置连接、认证、查询共享的 0.1–60 秒预算，
版本核验在连接预算之前。单次便利调用每次独立连接；显式会话复用自己的连接，
用自身 PID 正常认证，错误或会话释放时关闭。
报文长度上限 16 MiB，解压载荷上限 64 MiB；按 16 KiB 分块解压，明确拒绝超限、
截断或带额外尾部的压缩流。此上限是当前实验的资源限制，不是官方接口限制。
代码不启动 Python、不借用其他进程 PID，不提供任意 RPC 调用入口。

对外业务契约参考[官方 xtdata 文档](https://dict.thinktrader.net/nativeApi/xtdata.html)。
底层报文来自当前安装版本的已验证行为，并不是官方公布的稳定 TCP 协议。
五个版本指纹暂时与 `src/qmtcli/native_quote.py` 同步；不匹配就报错，不能推断
支持其他券商版本或大 QMT。

离线检查：

```powershell
cargo test --locked --manifest-path experiments/native-quote-rs/Cargo.toml
cargo clippy --locked --manifest-path experiments/native-quote-rs/Cargo.toml --all-targets -- -D warnings
cargo fmt --manifest-path experiments/native-quote-rs/Cargo.toml -- --check
```

当前范围只有行情快照。保留连接和心跳分流已有离线模拟端测试，真实 Rust 会话的
长时间联机验收仍待补测。时间戳可能来自缓存；不包含历史解码、实时推送、竞价语义、
账户查询和交易操作。实际运行与 SDK 对账的结果记录在同一
OpenSpec 的 `design.md`，避免把“编译成功”当作“接入验证通过”。

实测：Rust 独立 exe 已读回两股快照以及 `SH/SZ` 的 51,196 条缓存快照。
全市场结果与客户端自带 BSON 解码器逐字段、逐数值一致。与官方 SDK 的 JSON
返回比较时，14,086 个浮点值相差 1 ULP，其中 6 个超过 `1e-12` 绝对容差；
该严格 JSON 对账项仍记为未通过。两股的既定 SDK 对账通过，原始 BSON 对账无差异。
这验证了 Rust 原生请求和解码可用，不代表已经完整替代官方 SDK。
