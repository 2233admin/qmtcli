# qmtcli Agent Notes

This repository is a Python JSON CLI for local broker QMT / miniQMT and the bundled `xtquant` SDK.
It should be usable by any runtime that can launch a process and exchange stdin/stdout JSON.

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
- `src/qmtcli/daqmt_market.py` - the read-only loopback commands `qmtcli market` and
  `qmtcli account`. Read this before scripting against `127.0.0.1:9001`:
  `qmtcli account orders` prints today's orders with `status` and `status_name`,
  `qmtcli account trades` today's fills, `qmtcli account asset` the balance.
- `src/qmtcli/mcp_server.py` - stdio MCP server; tools generated from `AGENT_CAPABILITIES`,
  dispatched through `_handle_rpc_request`. Requires the optional `mcp` extra.
- `tests/` - fake `xtquant` modules; tests must not require real QMT.
- `examples/` - JSON and JSONL inputs for local automation.
- `bridge/` - the strategy that runs inside full QMT and serves `src/qmtcli` over loopback HTTP.
  `bridge/README.md` explains which copy the client actually loads and why editing this directory
  does not change a running bridge.
- `docs/repo-map.md` - which copy of this project you are editing (GitHub, this checkout, the
  `D:/projects/qmtcli` copy, LayerFS `qmtcli-20261024`) and which order policy each copy carries.
- `docs/qmt-client-diagnosis.md` - where the QMT client log lives, which port carries login versus
  market data, and the probe that tells a stopped bridge from a missing secret.
- `scripts/check_mcp_tree.py` - fails when the MCP server serves a different checkout than this
  one, or one with a different command surface.
- `scripts/check_bridge_copies.py` - the same check for the bridge: fails when the strategy file or
  the deployed assets are not this checkout's bytes.

## Tool Notes

- A `read` result is immediately editable: copy its `[FILE#TAG]` into `edit`. Re-read only after an
  edit or an external change, never as a precondition for each edit.
- After changing `bridge/`, run `python scripts/check_bridge_copies.py <qmt_root>`. `pytest` imports
  this checkout and stays green while the client runs old bytes, so only this check shows that the
  change reached the client.
- `bridge/` is excluded from `ruff format` (`[tool.ruff.format]` in `pyproject.toml`)
  because those files are sha256-pinned and deployed byte-identical elsewhere.
  `ruff check` still lints them; only the formatter steps back.

## Safety Boundaries

- Do not add real network serving to `server`; it is stdin/stdout JSONL only.
- Do not store credentials or account secrets.
- Do not auto-download, vendor, or install broker QMT.
- Do not place real orders in tests.
- Keep `data-call` and `trade-call` blocking `_`-prefixed methods.
- Keep order validation: positive price and positive A-share volume multiple of 100.
- Keep `server` as stdin/stdout JSONL, not TCP/HTTP.
- `buy` / `sell` / `cancel` stay available, backed by `QMTGateway.submit_order` and `cancel_order`;
  per-order human confirmation belongs to the calling gateway (KATANA). The MCP tool surface stays
  read-only: `mcp_server.py` excludes every capability whose danger is `places_order` or
  `cancels_order`, so order placement reaches an agent only through CLI, rpc or server, never
  through an MCP tool.
  History: `ad500c6` removed them after a 2026-10-19 unconfirmed 000963 sell order, and `73a6769`
  restored them on 2026-11-08 by operator decision.

## Common Agent Tasks

- To read the live bridge, use `qmtcli account` (Code Map) instead of a hand-rolled
  request carrying the secret from `connection.json`.
- For CLI behavior, add or update a small test in `tests/` first.
- For docs/examples, keep examples parseable and runnable through `qmtcli rpc` or `qmtcli server`.
- For QMT SDK behavior, fake `xtquant` with `types.ModuleType` in tests instead of importing broker SDK.
- For packaging, `pyproject.toml` reserves metadata; do not add publishing steps unless explicitly requested.
