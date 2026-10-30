# Acceptance contract

- Given a matching local MiniQMT build and explicit account, native `asset`
  returns account_type/account_id/cash/frozen_cash/market_value/total_asset.
- The backend works on Python 3.14 without importing xtquant.
- Given an unsupported platform/build, missing service, wrong account, malformed
  response, invalid numeric fields or timeout, return the existing error envelope;
  never fall back silently to the SDK or a persisted asset CSV.
- Only connect and asset-query message types are writable by this backend.
- An isolated subprocess owns native objects; hard timeout bounds native faults.
- Live financial data and account identifiers are excluded from committed tests
  and documentation. Fixtures use fictional data.
- CLI, RPC and capability/MCP discovery agree on supported options.

Known protocol evidence: 24-byte IPC envelope; connection request 12 bytes
(int64 session_id + int32 pid); asset account_id buffer is 24 bytes; response
is 76 bytes on the examined build. Tests and profile pinning must validate it.
