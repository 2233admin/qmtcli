# QMT host bridge

The code that runs *inside* the full QMT client, not the CLI. `src/qmtcli` talks to it over loopback HTTP.

| File | Role |
|---|---|
| `daqmt_server.py` | Bridge entry point. Loaded by QMT as a strategy; serves `/api/health`, `/api/capabilities`, `/api/call`, `/api/stream`. |
| `daqmt_api.py` | Resolves a catalog id to the native name the host injected, and refuses the ones it cannot reach. |
| `daqmt_codec.py` | Wire encoding for native values. |
| `daqmt_stream.py` | Subscribe and push frames for callbacks. |
| `catalog.json` | The 189 APIs / 410 targets of the 250807 SDK, with the mode and requirement flags the bridge enforces. |

## Why the entry point has two names

`daqmt_server.py` and the client's `D:/DFZQxtqmt_client_real_win64/python/大QMT.py` are byte-identical (`c9e0513315898306e3710805ac40dc664e9cf95b183e9b17c5e66b2d547924a6`). The installer copies one to the other; QMT loads the file under the name the operator picks. Only one copy lives here.

## Which copy the client runs, and why editing this directory does nothing

`connection.json` carries `resource_dir` and a sha256 for each of the five files above. At strategy start
`daqmt_server.py:94-104` requires `resource_dir` to be the directory that holds that `connection.json`,
then refuses to start unless every asset there matches its pinned digest. On this host:

```
C:/Users/Administrator/AppData/Local/QmtCli/daqmt/
```

So this directory is the source of truth, not the running code. Three consequences:

- Editing `bridge/daqmt_api.py` changes nothing the client loads.
- Editing the deployed copy without updating `connection.json.assets` makes the next strategy start fail
  with `invalid or modified bridge startup configuration`.
- The imported modules live for the whole strategy run, so even a correct edit needs a strategy restart.

`src/qmtcli/bootstrap.py --apply` copies only the entry point to `大QMT.py`; nothing in this repository
copies the four sibling assets. Treat `resource_dir` as owned by whatever wrote `connection.json`.

## What is deliberately absent

`connection.json` holds the bridge secret and the account number, so it never enters this repository. It lives at `C:/Users/Administrator/AppData/Local/QmtCli/daqmt/connection.json` with a DACL restricted to the current user and SYSTEM, and is written by the setup helper from values the operator supplies.

The fixed Rust CLI binary is absent for the same reason it is absent everywhere else: it is a 6 MB release artifact pinned by SHA-256, installed at `C:/Users/Administrator/AppData/Local/QmtCli/releases/7749aaec/qmtcli-rs.exe`, and accepted by digest rather than by file copy.

## Fresh host

Two commands, then the two GUI steps only a human can do (login, register the
strategy and tick auto-run).

```
uv run qmtcli bootstrap --account <资金账号> --qmt-root <QMT 安装目录>          # report only
uv run qmtcli bootstrap --account <资金账号> --qmt-root <QMT 安装目录> --apply  # install everything
```

`--apply` runs `qmtcli-rs setup` when `connection.json` is absent, copies `大QMT.py`
into `<QMT 安装目录>/python/`, deploys all five pinned assets into `resource_dir` and
retargets their digests in place.

Steps: `qmt_root` → `bridge_source` (sha256 must equal the constant in
`src/qmtcli/bootstrap.py`) → `strategy_file` (a differing file is reported, never
overwritten) → `fixed_release` (pinned SHA-256, never downloaded) → `connection`
(written by `qmtcli-rs setup`, which owns the secret and its DACL) → `bridge_assets`
(each pinned file present, byte-identical to the repository, and its digest recorded)
→ `assets_digests` (rewrites only that map) → `bridge_assets` again → `bridge_live`
(`--base-url` + `--secret` probe `/api/health` and `/api/account/asset`).
Exit 0 only when every step that applies is green; the GUI steps it cannot do are
printed under `manual_steps`.

A digest that does not match its file is reported even when the file itself is
correct. The strategy refuses to start on a mismatch, so checking the files alone
would report green on a config that cannot boot.

## Host requirements

The bridge refuses to start unless it is running as a complete strategy inside full QMT: it checks for `get_trade_detail_data` and, when trading is enabled, `passorder`, `cancel`, `can_cancel_order`, `ContextInfo.schedule_run` and `ContextInfo.cancel_schedule_run`. A missing name raises `Run the complete strategy directly inside full QMT` at `daqmt_server.py:1196-1203`.

Trading stays off unless `DAQMT_ALLOW_TRADING == '1'` (`:36`) or the config sets `trading_enabled`, and no request is served without a matching `X-Bridge-Secret` (`:322-328`).

## Order safety (2026-11)

Orders go through dedicated endpoints `/api/order/buy` and `/api/order/sell` only. The generic `/api/call` rejects `passorder`, `algo_passorder`, `smart_algo_passorder` and all backtest order functions (`order_shares`, `order_value`, etc.) with HTTP 403.

Dedicated endpoints accept only `prType=11` (limit orders). Market orders, algorithmic orders and smart-algo orders are rejected.

Validation order:
1. Price band: limit price must be within `[DownStopPrice, UpStopPrice]` and on the tick grid
2. Amount cap: `price * volume <= max_order_amount` (0 = no cap)
3. Contract detail missing or invalid → reject, fail closed

Dry-run (`"dry_run": true` in body or `dry_run: true` in `connection.json`) executes all validation but returns before `passorder`. It does not reserve an idempotency key.

Server-side idempotency: `user_order_id` is the reservation key. The bridge reserves it before validation, binds it to the full order intent (stock, price, volume, prType, direction), and uses it to detect duplicates. Same key + same terms → HTTP 200 `duplicate`. Same key + different terms → HTTP 409 `conflict`. Reservation is process-local; restart loses it but orders remain queryable by `orders()`.

After `passorder` returns, the bridge reads the order book back and looks for the row carrying `user_order_id` (three attempts, 0.2 s apart). Only then does it answer HTTP 202 `submitted`, with `order_id` and `broker_accepted: true`. This catches the case where QMT accepts the call and creates nothing: observed on a client whose trade channel was not ready after a restart, where `passorder` returned 0 and no order reached the book.

Unknown outcome: `passorder` exception, timeout, or a return with no matching row in the order book answers HTTP 502 `unknown` with `retry_safe: false`. The reservation moves to `outcome_unknown` and a later call with that key answers HTTP 409, never a duplicate. Do not auto-retry; query orders and deals first.

`passorder_form` in `connection.json` selects the overload: `full` (default, 11 arguments, carries `userOrderId` so the read-back matches the remark), `no_key` (10 arguments, no `userOrderId`, read-back matches a row that is new since the pre-submit snapshot and has the same stock, direction, price and volume), `minimal` (9 arguments, no `quickTrade` either). Only `full` was verified live. Switch the form when a QMT build or a trading mode silently drops one of them; the read-back tells you which one landed.

Trades use `DEAL` datatype (not `TRADE`). Each deal includes `user_order_id`, `order_id`, `commission`, `price`, `volume`, `amount` and `direction`.
