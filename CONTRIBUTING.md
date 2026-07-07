# Contributing

Keep changes small and local. This project is a thin bridge over a locally installed broker QMT
client, so avoid adding abstractions or dependencies unless they remove real duplication.

## Setup

```powershell
uv sync --extra dev
uv run --extra dev pytest -q
```

Real QMT is not required for tests. Tests should fake `xtquant` modules instead of depending on a
broker install.

## Before A Pull Request

Run:

```powershell
uv run --extra dev pytest -q
uv run --extra dev ruff check .
```

For changes touching account/order behavior, include a test that proves validation or RPC routing
without placing a real order.

## Release Notes

Update `CHANGELOG.md` under `Unreleased`. PyPI packaging is reserved, but publishing is not part of
the current GitHub workflow.
