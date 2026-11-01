# MiniQMT-first continuation — 2026-11-02

User priority is now MiniQMT completion; Big QMT extension is deferred.
Existing Rust executable 0.3.0 is unchanged, SHA-256
`236e39e7fc773edd2b01569c3c176cc85467aacc1c314ad04e4f1806cb83ffe6`.

## Current evidence

- Only XtItClient.exe (Big QMT) is running. Both installed real/test MiniQMT
  userdata roots have no up_queue_xtquant service queue. Native quote RPC to
  58610 with a one-second timeout failed with `connection timed out`.
- Formal runner actual-miniqmt preflight returns exit 2, status=blocked,
  passed=false, queue_present=false. No real account query was attempted.
- Re-ran existing full Rust parent/worker/installed-DLL synthetic acceptance:
  exit 0, passed=true. Forty four-section snapshots: one connection, 160 queries,
  zero service errors. Switching, identity rejection, timeout recovery, independent
  quote session, EOF and parent-death cleanup pass; no remaining owned workers.
  Final totals are 185 account queries over five explicitly created sessions.
- Added `experiments/accept_miniqmt.py`: explicit actual/synthetic scope,
  environment-only account input, summaries without identifiers/amounts/records,
  optional idle, healthy-session preservation after invalid input and owned-worker
  EOF checks. Uses existing psutil 7.2.2 solely as a development process checker;
  no Rust runtime or production dependency was added.
- Six initial validator tests failed with the missing implementation. After
  implementation and two additional consistency-marker cases, eight focused
  tests pass: `python -m pytest tests/test_miniqmt_acceptance.py -q`, exit 0.
- Formal runner against owned account and quote fixtures: exit 0, passed=true,
  scope=synthetic. Sixteen account queries and two quote queries, one connection
  each, zero fixture errors, generation retained and owned workers exited.
- `ruff check .` and `git diff --check`: exit 0. New script comments were checked
  for privacy, scope and process ownership. Rust sources were not changed; the
  previous 54 Rust tests remain baseline evidence, not a newly executed run.

First formal-runner synthetic attempt failed at quote phase because the replay
fixture requires the exact fixed stock order. The runner now uses that order;
the broker protocol was not changed. The failed receipt was preserved, and its
single leftover owned synthetic reply file was removed after path/time/ownership
checks. No recursive deletion or traversal into the fixture's vendor-bin junction.

Raw local receipts remain outside Git under
`F:\projects\_research\qmt-ida-20261031\recovery\`:
`rust-account-cli.json`, `formal-miniqmt-acceptance-synthetic.json`,
`formal-miniqmt-acceptance-fixture-order-failed.json`.
The blocked actual preflight is `dist/rust/miniqmt-preflight.json`.

## Remaining acceptance

MiniQMT must be started and logged in normally before running the actual profile.
The user was asked to switch using the existing normal client flow; no client was
closed, no credentials were requested, and no license/login configuration changed.
The prepared command is in rust/README.md; run with idle-seconds=65 for the real
retained-connection check. Account identity comes from the selected environment
variable and is never persisted in the report.

This is not MiniQMT completion. Actual four-section SDK field comparison,
real retained heartbeat/recovery, native history/subscriptions/auction semantics
and native account event consistency remain outstanding. Snapshot query replies
are not subscription events. No order/cancellation/transfer support is added.
Parent OpenSpec remains in_review. Prior Code Intel structural analysis timed
out at its provider node and remains unverified; this narrow test/tooling slice
used bounded direct inspection, not a claimed new structural gate pass.
