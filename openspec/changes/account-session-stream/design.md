# Design and source contracts

Use the existing XtQuantTrader lifecycle and callback API, verified in the installed
xtquant/xttrader.py: register_callback before start, subscribe(account), stop(). stop()
waits for callback executors, so callback threads only mark disconnection; the server
request owner performs cleanup/reconnect. Do not stop from inside a callback.

A small AccountSession owns one active gateway, keyed by requested path/account/type
and subscription mode. Avoid a global unbounded pool or result cache. Generation
and a lock coordinate callback publication; the synchronous request loop owns SDK
creation/query/close. No network listener or new dependencies. Reuse SDK lifecycle
rather than a new transport framework; local code only adapts it to JSONL ownership.

Snapshots perform four sequential current queries, not an atomic broker snapshot.
Sequence bounds expose overlap with delivered events. They do not implement an
authoritative materialized portfolio or deduplicate/reorder broker events.
Unsubscribe disables account JSONL forwarding; the account remains connected for
subsequent queries. Switching account ends the previous subscription.

Native asset remains crash-isolated and version-pinned. Do not infer native position
or order codecs from internal C++ structures. A combined snapshot may opt into that
asset path while the remaining three fields use the SDK; annotate the backend.

## Verification receipt (2026-11-01)

- Initial four regression tests failed for repeated connect, missing snapshot,
  account switch cleanup and failed snapshot recovery. The implementation passes
  those plus lifecycle, callback, isolation, deadlines and malformed-request checks.
- `uv run --no-sync --extra dev pytest -q`: 350 passed. Existing F:/projects/qmtcli/.venv
  reused via UV_PROJECT_ENVIRONMENT without syncing/modifying dependencies; pytest
  imports this worktree's src via repository configuration. Python 3.14 global
  environment was also used during development through uv --no-project.
- `uv run --no-sync --extra dev ruff check .` and `git diff --check`: pass.
  New AccountSession also passes ruff C901 complexity check.
- Actual JSONL dispatcher with synthetic gateway: same forty queries, forty new
  reads, connection creation 40 -> 1, final stop=1. Real gateway + fake SDK verifies
  register/start/connect/subscribe/stop each once. No claimed latency multiplier.
- Installed SDK source verified register_callback/start/subscribe/stop and the
  four public async query methods. Its synchronous method waits on Future.result()
  without a deadline; snapshot now uses async replies and one shared response budget.
- Python 3.14 launched a compatible Python 3.11 live worker. Asset, positions and
  orders returned on two attempts; four asset values were finite. Trade replies
  did not arrive. Snapshots correctly returned explicit deadline errors around 5s,
  with two connects/two clean stops due to invalidation. Full live snapshot failed;
  do not describe it as accepted. No forced disconnect or actual trade event was
  generated; real reconnect/event interleavings remain unverified.
- Live capture contains source hashes before the final malformed-command envelope
  guard; that final fix only concerns invalid JSON command types and is covered by
  the final full test run. Financial values and account identifiers stay out of repo.
- Code Intel normal completed before and after implementation. Local final analysis:
  C:/Users/Administrator/AppData/Local/code-intel/artifacts/qmtcli-account-session-stream/
  1793470759035-68340-core/run-complete.json. No second planning system was created.
- Private raw receipts remain under F:/projects/_research/qmt-ida-20261031/recovery/
  five-areas/qmtcli-session-baseline.json, qmtcli-session-after.json and
  qmtcli-account-session-live.json. No SDK verification worker remains running.

## Remaining acceptance

Current client's missing trade reply prevents a successful four-section live sample.
Do not replace it with an empty list or cached data. Real account event, recovery
and native full-account verification require suitable service responses/events.
Native asset still has per-request process/session overhead; this change does not
claim persistent native worker reuse or replace the complete SDK. MCP reuse is
within one snapshot, not across unrelated tools. Original main working files remain
untouched; branch depends on the still-unaccepted native asset base change.
