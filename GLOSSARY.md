# qmtcli 领域语言

qmtcli 在同一个仓库里对接四个互不相通的 QMT 运行面。这四个词经常被混用，混用会导致改错文件、重启错进程。

## 运行面

**大QMT**:
券商交付的完整客户端进程（`XtItClient.exe`）。交易策略在这个进程内部运行，能访问客户端已登录的资金账号。
_Avoid_: QMT, 主客户端, 完整版

**MiniQMT**:
同一套软件的最小模式（`userdata_mini`）。没有图形界面，独立的 xtquant 交易连接在这里才能建立。
_Avoid_: 迷你版, mini

**xtquant 直连**:
在 qmtcli 进程内构造 `XtQuantTrader` 直连 MiniQMT 交易服务。需要 MiniQMT 在跑，且账号服务队列存在。
_Avoid_: 原生连接, native 连接

**native 路由**:
qmtcli 自带的只读 IPC 通道，直连 MiniQMT 的 ringbuffer，不经过 CPython SDK 扩展。只能查，不能下单。
_Avoid_: xtquant 直连, 原生 API

**bridge 路由**:
大QMT 策略进程内开的 HTTP 面。qmtcli 通过它读资金和持仓、下单和撤单。
_Avoid_: 策略路由, daqmt 路由, 本地 HTTP

## 账户与委托

**资金账号**:
券商分配的账号，qmtcli 所有账户级操作都挂在它上面。一个 bridge 实例绑定一个。
_Avoid_: 账户, account, 用户

**可用数量**:
持仓里今天可以卖掉的股数。T+1 当天买入的部分不计入。卖出委托的股数不能超过它。
_Avoid_: can_use_volume, 可用持仓

**在途数量**:
已成交但未交收的股数，或者是已报未成的委托占用的股数。它不是可用数量。
_Avoid_: 冻结数量, 挂单数量

**委托**:
一次报给交易所的买卖指令，成交后变成一笔或多笔成交。
_Avoid_: 订单, order, 报单

**撤单**:
按系统委托号撤销一笔未成交的委托。只撤指定的那一笔，不动其他委托。
_Avoid_: 撤单请求, cancel, 全部撤单

**幂等键**:
客户端生成的 `user_order_id`，服务端用它防止重复提交。相同键和相同订单参数返回已有订单，相同键和不同参数返回 409 冲突。进程内有效，重启后丢失。
_Avoid_: idempotency key, user_order_id, 委托编号

**dry-run**:
预览模式。执行所有校验但不调用 `passorder`，不预留幂等键。返回规范化后的订单意图。
_Avoid_: 测试模式, 模拟下单

**未知结果**:
`passorder` 调用超时、异常，或者调用返回但委托簿里找不到这笔委托，无法确定券商是否接受。返回 `unknown` 并禁止自动重试，必须查询订单和成交后再决定。同一幂等键再次提交返回 409，不会返回重复。
_Avoid_: 失败, 错误, unknown

## 部署与验收

**桥接摘要**:
桥接进程启动时对部署的 `daqmt_server.py` 做的 SHA256。用来判断客户端里跑的是哪一版。
_Avoid_: 版本号, build hash, sha

**验收**:
只读地核对客户端里跑的桥接和磁盘上的部署是否一致，不下单。逐行报告，任何一行失败退出码 1。
_Avoid_: 自检, health check