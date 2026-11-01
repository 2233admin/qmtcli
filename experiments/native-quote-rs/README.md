# Rust 原生行情请求实验

问题：能否沿用官方 `get_full_tick(code_list)` 的业务接口，由 Rust 直接请求
MiniQMT，脱离 Python 和 xtquant 的运行时依赖？本目录用于验证这件事，尚未接入
QMTCLI 的正式后端，不是官方 Rust SDK。

在本工作树根目录执行：

```powershell
cargo run --locked --manifest-path experiments/native-quote-rs/Cargo.toml -- D:\DFZQxtqmt_client_real_win64 600000.SH 000001.SZ
```

编译后也可独立运行，不需要启动 Python：

```powershell
.\experiments\native-quote-rs\target\debug\qmt-native-quote-experiment.exe D:\DFZQxtqmt_client_real_win64 600000.SH 000001.SZ
```

程序输出 `{"ok":true,"data":{"600000.SH":{...},"000001.SZ":{...}}}`。
错误输出 `{"ok":false,"error":"..."}` 并以退出码 1 结束。
路径也可指向安装目录下的 `userdata_mini`。

Rust 库调用方式：

```rust,no_run
use qmt_native_quote_experiment::{QuoteClient, Result};

fn main() -> Result<()> {
    let client = QuoteClient::new(r"D:\DFZQxtqmt_client_real_win64");
    let ticks = client.get_full_tick(&["600000.SH", "000001.SZ"])?;
    println!("{ticks:?}");
    Ok(())
}
```

返回 `bson::Document`，保留官方“代码 → 字段”的映射、Int64 时间戳和深度数组。
`code_list` 也接受官方规定的市场代码，例如 `client.get_full_tick(&["SH", "SZ"])?`；
市场查询允许返回相应市场下的证券代码，仍拒绝无关市场的返回。
使用标准库 TCP，BSON 编解码复用 MongoDB 的 `bson` 库，zlib/CRC/SHA256
复用 `flate2`、`crc32fast`、`sha2`。`Cargo.lock` 固定完整依赖。
不会加载安装目录中的 DLL；读取五个二进制文件仅用于 SHA256 版本核验。

MiniQMT 必须已经运行。目标固定为 `127.0.0.1`，端口默认 58610，Rust 库可用
`with_port` 指定已有端口。`with_timeout` 设置连接、认证、查询共享的 0.1–60 秒预算，
版本核验在预算之前。每次查询独立连接并用自身 PID 正常认证，返回或出错后关闭。
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

当前范围只有行情快照。时间戳可能来自缓存；不包含行情长连接复用、历史解码、
实时推送、竞价语义、账户查询和交易操作。实际运行与 SDK 对账的结果记录在同一
OpenSpec 的 `design.md`，避免把“编译成功”当作“接入验证通过”。

实测：Rust 独立 exe 已读回两股快照以及 `SH/SZ` 的 51,196 条缓存快照。
全市场结果与客户端自带 BSON 解码器逐字段、逐数值一致。与官方 SDK 的 JSON
返回比较时，14,086 个浮点值相差 1 ULP，其中 6 个超过 `1e-12` 绝对容差；
该严格 JSON 对账项仍记为未通过。两股的既定 SDK 对账通过，原始 BSON 对账无差异。
这验证了 Rust 原生请求和解码可用，不代表已经完整替代官方 SDK。
