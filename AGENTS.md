# qmtcli

Python JSON CLI for a locally installed broker QMT / miniQMT client and its bundled `xtquant` SDK.
Any runtime that can launch a process and exchange stdin/stdout JSON can drive it; it does not install or vendor QMT.

## Commands

```powershell
uv sync --extra dev
uv run --extra dev pytest -q
uv run --extra dev ruff check .
uv run qmtcli capabilities
uv run qmtcli schema
uv run qmtcli examples
uv run qmtcli status
```

The verification gate is `uv run --extra dev pytest -q` plus `uv run --extra dev ruff check .`; CI runs the pytest step on Windows.
Use `uv run ...` unless the package is installed into the active global Python.

## Layout

- `src/qmtcli/cli.py`: argparse commands, JSON RPC, JSONL stdio loop, and `AGENT_CAPABILITIES`, the single command registry.
- `src/qmtcli/gateway.py`: QMT path discovery, SDK import, account/data/trade wrappers.
- `src/qmtcli/mcp_server.py`: stdio MCP server; tools generated from `AGENT_CAPABILITIES`,
  dispatched through `_handle_rpc_request`. Requires the optional `mcp` extra.
- `tests/`: fake `xtquant` modules; tests must not require real QMT.
- `examples/`: JSON and JSONL inputs for local automation.
- `scripts/check_doc_drift.py`: checks that every function on the official xtdata/xttrader doc pages appears in the alignment matrices in `docs/`; the weekly `doc-drift` workflow files an issue on drift.

## Conventions

Agent contract:

- Primary transport: stdin/stdout JSON through `qmtcli rpc` and JSONL through `qmtcli server`.
- Discovery commands: `qmtcli capabilities`, `qmtcli schema`, `qmtcli examples`.
- Stable success shape: `{"ok": true, "data": ...}`.
- Stable failure shape: `{"ok": false, "error": "..."}`.
- Request `id` is echoed when present.
- Do not require agents to parse README text to discover capabilities.

Safety boundaries:

- Keep `server` as stdin/stdout JSONL only; never add TCP/HTTP or other network serving.
- Do not store credentials or account secrets.
- Do not auto-download, vendor, or install broker QMT.
- Do not place real orders in tests.
- Keep `data-call` and `trade-call` blocking `_`-prefixed methods.
- Keep order validation: positive price and positive A-share volume multiple of 100.

Working rules:

- For CLI behavior, add or update a small test in `tests/` first.
- For docs/examples, keep examples parseable and runnable through `qmtcli rpc` or `qmtcli server`.
- For QMT SDK behavior, fake `xtquant` with `types.ModuleType` in tests instead of importing broker SDK.
- For packaging, `pyproject.toml` reserves metadata; do not add publishing steps unless explicitly requested.

## Change workflow

- Forward changes that alter commands, the agent contract, or trading behavior start as an OpenSpec change under `openspec/changes/`.
- Update `CHANGELOG.md` under `Unreleased`.
- Account or order changes include a test that proves validation or RPC routing without placing a real order.

## Agent skills

### Issue tracker

GitHub issues on `2233admin/qmtcli` (Primary). See `docs/agents/issue-tracker.md`.

### Triage labels

Workspace standard: one category label plus one state label per open issue. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: root `CONTEXT.md`; there is no ADR directory yet. See `docs/agents/domain.md`.

## References

- Changing an `xtdata` wrapper or field: read `docs/xtdata-alignment.md`.
- Changing an `XtQuantTrader` wrapper: read `docs/xttrader-alignment.md`.
- Contribution and release notes: read `CONTRIBUTING.md`.
