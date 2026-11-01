# 合成账户记录

asset/position/order/trade 的 `.bin` 使用本仓既有、已验收的布局生成，账户为虚构
`A`；`.json` 来自 `src/qmtcli/native_asset.py`、`native_records.py`、
`native_trades.py` 对同一合成记录的解码。未加载券商 DLL，没有真实账户或回报。
测试逐字段比较完整结果，并检验错误账户、截断、非有限数字、负数量和非法 UTF-8。

首次生成脚本的本机研究回执：
`F:/projects/_research/qmt-ida-20261031/make-rust-account-fixtures.py`。
fixture 独立随仓库保存，运行 Rust 测试不需要该脚本或 Python。
