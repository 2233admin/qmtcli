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

Two addresses are configured and they do different jobs:

| Key | File | Port | Job |
|---|---|---|---|
| `m_strSeviceAddress = g_xtservice_address` | `config/clientEnv.lua:36` | 56000 | Trading session login. This is the one that must be reachable to trade. |
| `m_strProxyAddress = g_defaultPorts["proxy"]` | `config/clientEnv.lua:47` | 59000 | Proxy and market-data channel. |

A reachable 59000 with a dead 56000 means the host and network are fine and only the trading service is down. Reaching for 59000 as a workaround does not produce a login.

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

## Separating broker-side from local

A TCP probe distinguishes the two without touching the client:

| Observation | Conclusion |
|---|---|
| 56000 times out on every login host, 59000 connects | broker-side service problem; no local fix |
| 56000 refuses (RST) on every host | service process down on the broker host |
| 56000 and 59000 both time out | local network or egress problem |

The three login hosts come from `config/customer.lua` → `xtaddress.server`.
