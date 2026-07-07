# qmtcli

Small CLI for local QMT/XtQuant.

It discovers the broker-bundled `xtquant` SDK, runs diagnostics, exposes market-data calls, and wraps basic account/order operations for local automation.

## Install

```powershell
pip install -e .[dev]
```

QMT itself is not downloaded or vendored. Install and log in to your broker QMT / miniQMT client first.

## Commands

```powershell
qmtcli status
qmtcli doctor
qmtcli calendar
qmtcli sector-list
qmtcli sector-stocks 沪深A股
qmtcli full-tick 600519.SH 000001.SZ
qmtcli bars 600519.SH --period 1d --count 100
qmtcli l2-quote 600519.SH
qmtcli data-call get_cb_info --args "[\"123001.SZ\"]"
```

Account commands need `--account`:

```powershell
qmtcli --account ACCOUNT_ID asset
qmtcli --account ACCOUNT_ID positions
qmtcli --account ACCOUNT_ID orders
qmtcli --account ACCOUNT_ID trades
qmtcli --account ACCOUNT_ID buy 600519.SH 100 1500.00
qmtcli --account ACCOUNT_ID sell 600519.SH 100 1500.00
qmtcli --account ACCOUNT_ID cancel ORDER_ID
```

JSON stdin/stdout:

```powershell
echo {"command":"status"} | qmtcli rpc
qmtcli server
```

## Path

Pass either a QMT install root or `userdata_mini`:

```powershell
qmtcli --path D:\DFZQxtqmt_client_real_win64 doctor
qmtcli --path D:\DFZQxtqmt_client_real_win64\userdata_mini --account ACCOUNT_ID asset
```

Known default roots are checked automatically:

- `D:\DFZQxtqmt_client_real_win64`
- `D:\DFZQxtqmt_client_test_win64`
- `C:\DFZQxtqmt_client_real_win64`
- `C:\DFZQxtqmt_client_test_win64`

## Test

```powershell
python -m pytest -q
```
