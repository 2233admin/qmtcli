# MiniQMT native asset query

Status: in_review. Principal acceptance and merge remain pending.

User request: implement MiniQMT account assets first and update QMTCLI, following
the investigation into replacing the Python-version-bound xtquant SDK.

Add an opt-in native backend for `asset`, preserving the SDK default and JSON
envelope. Native means direct local IPC through the client's ringbuffer runtime;
it does not import xtquant or its CPython extensions. It still requires a matching
Windows x64 MiniQMT installation. Do not claim this is a vendor-independent ABI.

Scope: connection handshake, one account asset query, timeout/error handling,
offline fixtures and an explicitly recorded live read-only check if available.
Exclude orders, cancellations, transfers, market data, big-QMT support and SDK
replacement for other commands.

The latest upstream read-only policy remains in force. Original checkout and
its uncommitted files are untouched. Work is based on origin/main ad500c6.
