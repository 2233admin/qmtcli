# Account sessions, snapshots and event streaming

Status: in_review. Full four-section JSONL acceptance now passes on the pinned
MiniQMT build with explicit trades_backend=native. Not merged or registered on a
task board. SDK-only trade replies and real event/reconnect interleavings remain
separate unverified paths; do not label the entire SDK/software restored.

The user authorized persistent connection reuse, one account-wide read, incremental
subscriptions and incremental native access. The actual JSONL dispatcher currently
creates 40 gateways/connections for 40 repeated account requests (synthetic gateway
counter; no latency measurement). Reuse one active SDK account session per server.
Add account-snapshot and server-only account_subscribe/account_unsubscribe.

Acceptance follow-up: the user correctly identified that green offline tests did
not finish the four-section deliverable. The installed SDK trade query timed out,
while the native query returned actual nonempty trades. Add an explicit pinned
native trade backend, sharing the existing transport and asset validation. No
timeouts become empty lists and no hidden backend fallback is added.

Base: 3efc73a, including the existing native-asset change, whose principal acceptance
is still pending. This work is isolated from main's uncommitted files. Workspace
_standards/repo-standard.md and _standards/kit are missing; existing OpenSpec form
is followed without claiming template compliance. No external tracker is selected.
