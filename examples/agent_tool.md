# Local Process Tool Example

`qmtcli` can be exposed to any runtime as a local process tool. It is not tied to a specific agent
framework. OpenClaw, Hermes, Codex, Claude, Cursor-style agents, custom schedulers, and plain scripts
can all use the same stdin/stdout JSON contract.

## Tool

- Name: `qmtcli`
- Command: `qmtcli`
- Primary mode: stdin JSON with `rpc`, or stdin/stdout JSONL with `server`
- Network: none
- Credentials: none stored by this tool; QMT login stays in the local broker client

## Discovery

Run these before trading:

```powershell
qmtcli capabilities
qmtcli schema
qmtcli examples
qmtcli doctor
```

## One-Shot Request

```powershell
Get-Content examples\status.json | qmtcli rpc
```

Equivalent request body:

```json
{"id":"status-1","command":"status"}
```

## JSONL Session

Start:

```powershell
qmtcli server
```

Send one request per line:

```jsonl
{"id":"cap-1","command":"capabilities"}
{"id":"data-1","command":"data_call","method":"get_stock_list_in_sector","args":["沪深A股"]}
```

## Dangerous Actions

Treat these as requiring explicit user approval in any agent policy:

- `buy` - places an order
- `sell` - places an order
- `cancel` - cancels an order
- `trade_call` - arbitrary public `XtQuantTrader` method

`data_call` is an escape hatch for public `xtquant.xtdata` methods. It is usually read-only, but
agents should still inspect the requested method before calling it.

## Response Contract

Success:

```json
{"ok":true,"data":{},"id":"optional-echo"}
```

Failure:

```json
{"ok":false,"error":"message","id":"optional-echo"}
```
