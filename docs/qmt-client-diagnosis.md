# Diagnosing a QMT client that will not log in or will not load the bridge

Read this before opening client config files: it names the four places the answers live.

## Where the client log is

The client writes to `D:/DFZQxtqmt_client_real_win64/userdata/log/XtClient_YYYYMMDD.log`. That path is not configured directly; it comes from the `DatePattern` lines in `config/xtclient.log4cxx`:

```
log4j.appender.fa1.DatePattern='../userdata/log/XtClient_'yyyyMMdd'.log'
```

The log answers login questions directly. `[TC::CProxyClient::onConnected]` lines carry `remote_addr` and `m_status`; `m_status = 12` is a successful login, `status = 4` is connecting, `5` is connected-then-dropped, and `10060` is a TCP connect timeout.

```
CProxyClient::onConnected  remote_addr = 101.230.66.158:56000  m_status = 12.   ← logged in
CProxyClient::onConnected  ... bson_error = "End of file", isNetError: true     ← server closed mid-session
10060                                                                            ← TCP never established
```

## Which port does what

`config/clientEnv.lua` carries two addresses:

| Key | Line | Port | Configured role |
|---|---|---|---|
| `m_strSeviceAddress = g_xtservice_address` | `:36` | 56000 | trading service, from `xtaddress.server` |
| `m_strProxyAddress = g_defaultPorts["proxy"]` | `:47` | 59000 | proxy, from `xtaddress.proxy` |

The client's own runtime record disagrees about which port carries trading. `XtClient_YYYYMMDD.log` writes this on shutdown:

```
[TC::CQuotersConfig::flush] ... servers = [1 : server num 0, current , trade current 1_1_101.230.66.158_59000]
                              [2 : server num 13, current 0_2_43.242.96.162_55300,
                                   trade current 1_2_140.206.172.170_59000]
```

`trade current` names 59000, and it names a host `43.242.96.162:55300` that appears in no `customer.lua` list. The `m_status` values in the same log show the login attempts going to 56000. Treat the mapping as unresolved: read `trade current` from a live logged-in client instead of deriving it from the config.

## Which customer.lua wins

`config/customer.lua` ships with the installer; `config_local/customer.lua` is the per-install override and is the one in effect. Their addresses must match, because both carry `xtaddress.server` (56000) and `xtaddress.proxy` (59000).

## Confirming the bridge is up

```bash
"C:/Users/Administrator/AppData/Local/QmtCli/releases/7749aaec/qmtcli-rs.exe" \
  sdk-capabilities --config "C:/Users/Administrator/AppData/Local/QmtCli/daqmt/connection.json"
```

| Output | Meaning |
|---|---|
| exit 0 with `"ok":true` | bridge is listening |
| exit 1 with `os error 10061` | nothing is listening: strategy not running, or already stopped |
| exit 1 with `403` | `X-Bridge-Secret` mismatch |
| exit 1 with `400` | account in `connection.json` disagrees with the bridge |

The `10061` arm doubles as the stopped-bridge criterion: stop the strategy in QMT, rerun, and the probe must return to `10061`.

## TCP probes prove nothing behind the TUN proxy

While a TUN proxy (verge-mihomo) is active, every non-loopback TCP connect succeeds in 0–2 ms, including addresses that cannot exist. Measured 2026-11-08 15:16 +08:00:

| Target | connect | first read |
|---|---|---|
| `192.0.2.1:56000` (RFC 5737, unroutable) | ok, 1 ms | — |
| `203.0.113.7:59000` (RFC 5737) | ok, 26 ms | — |
| `127.0.0.1:1` | refused `10061` | — |
| `github.com:22` | ok, 416 ms | `SSH-2.0-…` |
| all three login hosts, 56000 | ok, ~0 ms | nothing for 4 s |
| all three login hosts, 59000 | ok, 28–52 ms | immediate zero-byte EOF |

The `192.0.2.1` row settles it: an address that cannot be routed still connects. Loopback still refuses, so the hijack covers every non-loopback destination and nothing else.

Read the set, not one row. `github.com:22` returning a banner shows the proxy forwards application data, so a target returning zero bytes on every port means only that **this host cannot reach the target** — never that the server is down.

Signals the proxy cannot fake:

| Signal | Meaning |
|---|---|
| `XtClient_*.log` holds `m_status = 12` for the current login attempt | the client genuinely logged in |
| `sdk-capabilities` exits 0 with `"ok":true` | the bridge is answering on loopback |
| `sdk-capabilities` exits 1 with `os error 10061` | nothing is listening on loopback: bridge not started, or already stopped |

The three login hosts come from `config/customer.lua` → `xtaddress.server`, but a probe of them carries no verdict while the proxy is up.
