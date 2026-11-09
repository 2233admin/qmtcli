# QMT host bridge

The code that runs *inside* the full QMT client, not the CLI. `src/qmtcli` talks to it over loopback HTTP; this directory is what the client loads.

| File | Role |
|---|---|
| `daqmt_server.py` | Bridge entry point. Loaded by QMT as a strategy; serves `/api/health`, `/api/capabilities`, `/api/call`, `/api/stream`. |
| `daqmt_api.py` | Resolves a catalog id to the native name the host injected, and refuses the ones it cannot reach. |
| `daqmt_codec.py` | Wire encoding for native values. |
| `daqmt_stream.py` | Subscribe and push frames for callbacks. |
| `catalog.json` | The 189 APIs / 410 targets of the 250807 SDK, with the mode and requirement flags the bridge enforces. |

## Why the entry point has two names

`daqmt_server.py` and the client's `D:/DFZQxtqmt_client_real_win64/python/大QMT.py` are byte-identical (`c9e0513315898306e3710805ac40dc664e9cf95b183e9b17c5e66b2d547924a6`). The installer copies one to the other; QMT loads the file under the name the operator picks. Only one copy lives here.

## What is deliberately absent

`connection.json` holds the bridge secret and the account number, so it never enters this repository. It lives at `C:/Users/Administrator/AppData/Local/QmtCli/daqmt/connection.json` with a DACL restricted to the current user and SYSTEM, and is written by the setup helper from values the operator supplies.

The fixed Rust CLI binary is absent for the same reason it is absent everywhere else: it is a 6 MB release artifact pinned by SHA-256, installed at `C:/Users/Administrator/AppData/Local/QmtCli/releases/7749aaec/qmtcli-rs.exe`, and accepted by digest rather than by file copy.

## Fresh host

One command reports every deployment fact with its digest, and installs the
bridge file with `--apply`:

```
uv run qmtcli bootstrap --account <资金账号> --qmt-root <QMT 安装目录>          # report only
uv run qmtcli bootstrap --account <资金账号> --qmt-root <QMT 安装目录> --apply  # copy 大QMT.py in
```

Steps: `qmt_root` → `bridge_source` (sha256 must equal the constant above) →
`strategy_file` (a differing file is reported, never overwritten) →
`fixed_release` (pinned SHA-256, never downloaded) → `connection` (written by
`qmtcli-rs setup`, which owns the secret and its DACL) → `bridge_live`
(`--base-url` + `--secret` probe `/api/health` and `/api/account/asset`).
Exit 0 only when every step that applies is green; the two GUI steps it cannot
do are printed under `manual_steps`.

## Host requirements

The bridge refuses to start unless it is running as a complete strategy inside full QMT: it checks for `get_trade_detail_data` and, when trading is enabled, `passorder`, `cancel`, `can_cancel_order`, `ContextInfo.schedule_run` and `ContextInfo.cancel_schedule_run`. A missing name raises `Run the complete strategy directly inside full QMT` at `daqmt_server.py:1196-1203`.

Trading stays off unless `DAQMT_ALLOW_TRADING == '1'` (`:36`) or the config sets `trading_enabled`, and no request is served without a matching `X-Bridge-Secret` (`:322-328`).
