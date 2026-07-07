# qmtcli Agent Notes

This repository is an agent-first Python CLI for local broker QMT / miniQMT and the bundled
`xtquant` SDK. It should be usable by any agent runtime, including OpenClaw, Codex, Claude, and
plain scripts.

## Agent Contract

- Primary transport: stdin/stdout JSON through `qmtcli rpc` and JSONL through `qmtcli server`.
- Discovery commands: `qmtcli capabilities`, `qmtcli schema`, `qmtcli examples`.
- Stable success shape: `{"ok": true, "data": ...}`.
- Stable failure shape: `{"ok": false, "error": "..."}`.
- Request `id` is echoed when present.
- Do not require agents to parse README text to discover capabilities.

## First Commands

```powershell
uv sync --extra dev
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run qmtcli capabilities
uv run qmtcli schema
uv run qmtcli examples
uv run qmtcli status
uv run python -m qmtcli status
```

Use `uv run ...` unless the package is installed into the active global Python.

## Code Map

- `src/qmtcli/cli.py` - argparse commands, JSON RPC, JSONL stdio loop.
- `src/qmtcli/gateway.py` - QMT path discovery, SDK import, account/data/trade wrappers.
- `tests/` - fake `xtquant` modules; tests must not require real QMT.
- `examples/` - JSON and JSONL inputs for local automation.

## Safety Boundaries

- Do not add real network serving to `server`; it is stdin/stdout JSONL only.
- Do not store credentials or account secrets.
- Do not auto-download, vendor, or install broker QMT.
- Do not place real orders in tests.
- Keep `data-call` and `trade-call` blocking `_`-prefixed methods.
- Keep order validation: positive price and positive A-share volume multiple of 100.
- Keep `server` as stdin/stdout JSONL, not TCP/HTTP.

## Common Agent Tasks

- For CLI behavior, add or update a small test in `tests/` first.
- For docs/examples, keep examples parseable and runnable through `qmtcli rpc` or `qmtcli server`.
- For QMT SDK behavior, fake `xtquant` with `types.ModuleType` in tests instead of importing broker SDK.
- For packaging, `pyproject.toml` reserves metadata; do not add publishing steps unless explicitly requested.
