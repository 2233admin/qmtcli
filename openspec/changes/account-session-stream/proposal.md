# Account sessions, snapshots and event streaming

Status: in_review. Local implementation and automated checks pass; not merged or
registered on a task board. Current live integration remains incomplete because
the installed client's trade query does not deliver a response within the budget.

The user authorized persistent connection reuse, one account-wide read, incremental
subscriptions and incremental native access. The actual JSONL dispatcher currently
creates 40 gateways/connections for 40 repeated account requests (synthetic gateway
counter; no latency measurement). Reuse one active SDK account session per server.
Add account-snapshot and server-only account_subscribe/account_unsubscribe.

Base: 3efc73a, including the existing native-asset change, whose principal acceptance
is still pending. This work is isolated from main's uncommitted files. Workspace
_standards/repo-standard.md and _standards/kit are missing; existing OpenSpec form
is followed without claiming template compliance. No external tracker is selected.
