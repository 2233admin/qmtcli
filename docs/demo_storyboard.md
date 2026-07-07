# Demo GIF Storyboard

Use this as the script for a short README GIF. Keep it under 20 seconds.

## Scene 1: Discovery

```powershell
qmtcli capabilities
```

Show that the tool prints JSON with `protocol`, `transports`, and danger labels.

## Scene 2: Schema

```powershell
qmtcli schema
```

Show `ok`, `data`, `error`, and echoed `id`.

## Scene 3: One-Shot RPC

```powershell
Get-Content examples\status.json | qmtcli rpc
```

Show `{"ok":true,...}`.

## Scene 4: Agent Loop

```powershell
qmtcli server
```

Paste:

```jsonl
{"id":"cap-1","command":"capabilities"}
{"id":"ex-1","command":"examples"}
```

Show one JSON response per line.

## Caption

Any agent runtime that can launch a process and exchange JSON can use local QMT through `qmtcli`.
