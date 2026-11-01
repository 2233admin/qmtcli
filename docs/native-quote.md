# 原生行情快照

`full-tick` 可显式选择 `native`，返回与 SDK 相同的证券代码到快照的映射。
默认仍为 `sdk`；原生失败会报错，不会自动切换 SDK。不需要交易账户。

```powershell
python -m qmtcli --path D:\DFZQxtqmt_client_real_win64 full-tick 600000.SH 000001.SZ --backend native
```

通过 `rpc` 或常驻 JSONL `server` 发送：

```json
{"id":1,"command":"full_tick","backend":"native","path":"D:\\DFZQxtqmt_client_real_win64","symbols":["600000.SH","000001.SZ"],"timeout":5,"quote_port":58610}
```

RPC/JSONL 使用标准 `{ok,data,id}` / `{ok,error,id}` 包装；直接 CLI 保留原来的
快照输出。MCP 的 `qmt_full_tick` 使用相同参数和分发入口。`capabilities`、
`schema`、`examples` 可发现这项能力。

原生模式通过标准库 socket 连接已经运行的本机 miniquote 服务，仅允许正常的
当前进程 PID 认证和 `getFullTick`。地址固定为 `127.0.0.1`，端口默认 58610，
可用 `--quote-port` / `quote_port` 指定已有服务端口；不会启动网络服务器。
`timeout` 限制连接、认证和查询的共同预算（0.1–60 秒），本地版本校验和
BSON 模块加载发生在该预算之前。最多每次 1000 个代码，每个最多 64 个 ASCII 字符。

不导入 `xtquant`，不加载其 CPython 扩展。复用安装目录中的 `xtbson.bson37`
纯 Python 实现，通过私有包名和相对导入加载；不修改 `sys.path`，不分发券商代码，
不安装新的 BSON 包。自定义实现仅负责已验证的报文封装、校验和命令适配。

支持范围限定为当前 Windows x64 MiniQMT 安装版本，运行时逐一检查
`miniquote.exe`、`QuoteCenter_mini.dll`、`quoter.dll`、`net.dll`、`utils.dll`
的 SHA256（常量见 `src/qmtcli/native_quote.py`）。升级后的指纹不匹配会明确失败，
需要重新验证，不能据此推断支持大 QMT 或其他券商版本。

快照保留服务端原始 `time`，可能是休市时的缓存。空映射表示该查询没有可用快照，
不代表获得了最新行情。浮点数与 SDK 的 JSON 序列化可能相差约 1e-15，
实测逐字段对账使用 1e-12 的绝对容差；整数、字段和数组长度严格比较。

每次快照创建并关闭自己的连接，JSONL 进程仍可复用。此前长时间下载探针遇到一种
尚未识别的报文，因此行情连接复用还未验收。此功能不包含历史压缩载荷解码、
实时订阅推送或集合竞价字段语义验收，不能视为完整替代 xtquant。
