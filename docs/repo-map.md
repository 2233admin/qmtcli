# Where the code lives

Four copies of this project exist on this machine. Check which one you are editing before the first
edit; an edit in one is invisible in the others and nothing syncs them.

| Copy | Path | What it is |
|---|---|---|
| GitHub | `https://github.com/2233admin/qmtcli`, branch `main` | Published product. Canonical for anything shipped by `uv`/pip. `origin/main` currently points at `ad500c6`, the read-only release. |
| This checkout | `F:/projects/qmtcli` | Clone of the above, branch `layerfs-backup-20261108`. Working copy for edits and for `uv run --extra dev pytest -q`. It carries the restored order capability (`73a6769`) and is the tree the MCP server runs. |
| The `D:` copy | `D:/projects/qmtcli` | An older clone (`c6b356e`) with its own venv, where the broker `xtquant` was installed first. The MCP server no longer runs from it. |
| LayerFS | project `qmtcli-20261024`, branch `main` | Working source for the QMT native bridge work. Not a git repository; reached through the `layerfs` / `layerfs_script` tools. |

## Order policy per copy

| Copy | `buy` / `sell` / `cancel` over CLI/rpc/server | MCP tool surface | `trade-call` |
|---|---|---|---|
| This checkout (`F:`) | present | excluded (`mcp_server.py` drops `places_order` / `cancels_order`) | unrestricted except `_`-prefixed methods |
| `origin/main` (`ad500c6`) | absent | absent | `query_*` / `smt_query_*` only (`READ_ONLY_TRADER_PREFIXES`) |
| The `D:` copy (`c6b356e`) | present | excluded | unrestricted except `_`-prefixed methods |
| LayerFS `qmtcli-20261024` `main` | present | excluded | unrestricted except `_`-prefixed methods |

Per-order human confirmation belongs to the calling gateway (KATANA), not to qmtcli. An MCP client
can never place an order: `mcp_server.py` excludes every capability whose danger is `places_order`
or `cancels_order`, so the order path stays CLI/rpc/server only.

## Check before you start

```bash
git -C F:/projects/qmtcli fetch origin
git -C F:/projects/qmtcli rev-list --left-right --count origin/main...HEAD
```

The left number is how many commits `origin/main` has that the checkout lacks. A non-zero left
number means the published product has moved; read `git -C F:/projects/qmtcli log --oneline
HEAD..origin/main` before editing.

## The MCP server serves this checkout

`~/.omp/agent/mcp.json` starts the qmt server with `--directory F:/projects/qmtcli`, so every
`qmt_*` tool answers from this checkout and follows its edits. The server runs in its own
environment (`UV_PROJECT_ENVIRONMENT` under `~/.omp/agent/`), so the checkout's dev venv stays
untouched.

Run `python scripts/check_mcp_tree.py` to see which tree is served and to fail on a command surface
that differs from this checkout's.

## What is only in LayerFS

`handoffs/`, `recovered/`, `recovery-input/`, `tools/`, and `docs/sdk/` exist only in LayerFS.
`handoffs/`, `recovered/`, and `recovery-input/` are evidence from native-bridge investigation and
are not product. `tools/` and `docs/sdk/` are the official 250807 SDK semantic map.

## What is not in either store

`README_OLD.md`, `README_BEFORE_POLISH.md`, and `.github-optimization.md` are superseded drafts, not
product. They are ignored by git in this checkout.

## Interpreters

`py -V:3.15` (Python 3.15.2) lives at `%LOCALAPPDATA%\Python\pythoncore-3.15-64`, with its shims in
`%LOCALAPPDATA%\Python\bin`. On 2026-11-09 a Python install manager put a 3.15 store inside this
checkout as `Python/`, which made `ruff check .` report 2768 errors from the CPython stdlib. It was
moved to the address above on 2026-11-10; `HKCU\Software\Python\PythonCore\3.15` now points there,
and the pre-move values are backed up at
`%LOCALAPPDATA%\Python\pythoncore-3.15-regbackup.reg`. No interpreter belongs inside the repo, so a
`Python/` directory reappearing here is an accident, not product.
