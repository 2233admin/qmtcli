# MiniQMT-first continuation — 2026-11-02

User priority is now MiniQMT completion; Big QMT extension is deferred.
Existing Rust executable 0.3.0 is unchanged, SHA-256
`236e39e7fc773edd2b01569c3c176cc85467aacc1c314ad04e4f1806cb83ffe6`.

## Current evidence

- Before 05:52, only XtItClient.exe (Big QMT) was running. Both installed real/test MiniQMT
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

### Login rejection observed after normal startup

At 05:52 the user started MiniQMT. XtMiniQmt.exe and miniquote.exe are present;
the account queue is still absent and the native quote read on 58610 still times
out. The actual blocker is now failed login authorization, not a missing process.
Its login callback logs `status=23` and the exact message
`请联系券商开通对应权限`. This is the client-observed callback status; the raw
server response and any local status translation have not been independently
decoded, so do not claim that 23 is necessarily the server's original error code.

Same login identity (compared in memory, not persisted), same configured endpoint,
same reported client version 2.0.24.0: Oct 29 04:30:36 records status 9 and loads
permissions; Nov 1 17:31/17:33/17:34 records status 23; Nov 2 05:51/05:52 repeats
the rejection. The Nov 1 rejection predates the Nov 2 02:29 Qt SSL change and the
Rust public-read update. This excludes those later changes as the initial trigger,
not every possible earlier environment/client/server change.

An additional observed difference is the missing CPU identifier suffix in the
client's local-info string. CPU model, MAC comparison, serial comparison and host
comparison match the prior successful login. Current Windows CIM can still read
the processor identifier. This is a client/device-identification clue, not a
proven cause of the authorization failure. License expiry, permission changes,
device binding, login response translation and service maintenance remain
unverified. No account/device IDs were retained in the sanitized comparison.

The WMIC executable is absent on this Windows build. Installed utils.dll contains
both WMI ProcessorId/Win32_Processor strings and WMIC commands for other hardware
queries; that does not establish that missing WMIC caused the CPU identifier gap.
No Windows capability, client file, account permission or device identity was
changed. Read-only Windows capability enumeration required elevation and was not
pursued because it is unnecessary for the observations above. The sanitized
comparison is `recovery/mini-login-permission-comparison.json` under the existing
research directory; raw logs remain in the installed MiniQMT log directory.

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
