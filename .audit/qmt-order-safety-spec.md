## Problem Statement

脚本通过 bridge 路由提交委托时，当前实现无法可靠区分有效限价单、重复请求、未知提交结果和应拒绝的通用下单调用。调用方可能在价格或数量错误时把请求发到券商，也可能在请求超时后重复提交。当前工作区还缺少 `daqmt_market.py` 的现行 LayerFS 基线，无法安全地验证这些行为。

## Solution

在现行 LayerFS 源码分支上完成 bridge 路由的限价委托安全边界。调用方通过 CLI、rpc 或 server 提交买卖委托时，bridge 先校验完整订单意图，再决定是否调用 `passorder`。专用买卖入口只接受 `prType=11` 的限价单。幂等键绑定完整订单意图，重复请求返回已有委托，键冲突返回错误。提交结果未知时返回 `outcome_unknown`，禁止自动重试。通用 API 不调用真实下单函数，但保留撤单和查询。

## User Stories

1. As a script operator, I want to submit a buy or sell order through the bridge route, so that I can automate full QMT without xtquant 直连.
2. As a script operator, I want the bridge to accept only `prType=11` limit orders on the dedicated buy and sell endpoints, so that unsupported price types cannot bypass the safety checks.
3. As a script operator, I want the bridge to reject non-positive prices and invalid volumes before submission, so that malformed requests never reach `passorder`.
4. As a script operator, I want the bridge to reject volumes that are not positive multiples of 100, so that A-share lot-size errors are caught locally.
5. As a script operator, I want the bridge to enforce the configured maximum order amount, so that a mistaken quantity or price cannot create an unexpectedly large order.
6. As a script operator, I want the bridge to reject a limit price above the contract upper price limit, so that the order does not fail only at the broker.
7. As a script operator, I want the bridge to reject a limit price below the contract lower price limit, so that invalid prices are caught before submission.
8. As a script operator, I want the bridge to reject a limit price that is not on the contract tick grid, so that price precision errors are reported locally.
9. As a script operator, I want missing or invalid contract details to fail loudly, so that the bridge never treats unavailable price limits as permission to submit.
10. As a script operator, I want invalid `max_order_amount` configuration to fail at strategy startup, so that a malformed safety limit cannot silently disable the cap.
11. As a script operator, I want dry-run to perform the same validation as a real submission without calling `passorder`, so that I can test an order safely.
12. As a script operator, I want dry-run to reserve no idempotency key, so that a rejected preview cannot block a later real request.
13. As a script operator, I want dry-run to return the normalized order intent, so that I can inspect the stock, side, volume, price, price type and idempotency key before submission.
14. As a script operator, I want a supplied idempotency key to be required for real submission, so that retries have a stable identity.
15. As a script operator, I want the bridge to bind an idempotency key to the full normalized order intent, so that the same key cannot submit a different stock, side, volume or price.
16. As a script operator, I want an exact duplicate request to return the existing order, so that a retry after a lost response does not submit twice.
17. As a script operator, I want an idempotency key reused with different order terms to return a conflict, so that accidental key reuse is visible.
18. As a script operator, I want duplicate lookup to check both today's orders and today's deals, so that a filled order is recognized as an existing request.
19. As a script operator, I want duplicate lookup failure to block submission, so that a failed broker query is never interpreted as no matching order.
20. As a script operator, I want concurrent requests with the same idempotency key to submit only one order, so that parallel retries cannot duplicate a broker request.
21. As a script operator, I want the bridge to serialize lookup, reservation and submission for one idempotency key, so that two requests cannot pass the duplicate check at the same time.
22. As a script operator, I want a submission reservation to be recorded before `passorder`, so that a timeout or process interruption cannot cause a blind retry.
23. As a script operator, I want an exception from `passorder` to return `outcome_unknown`, so that I do not assume the broker rejected the order.
24. As a script operator, I want a negative return code from `passorder` to report a failed submission, so that native failures are not reported as success.
25. As a script operator, I want an `outcome_unknown` result to set `retry_safe` to false, so that callers can distinguish it from a safe retry.
26. As a script operator, I want an uncertain idempotency reservation to remain reserved for the bridge process lifetime, so that a later request does not resubmit the same key.
27. As a script operator, I want completed duplicate replays to work without revalidating current cash, positions or contract details, so that a delayed response does not create a false rejection.
28. As a script operator, I want idempotency scope to include the startup-bound account, so that two account contexts cannot share one reservation.
29. As a script operator, I want idempotency persistence to be documented as process-local, so that I do not assume restart-safe exactly-once behavior.
30. As a script operator, I want a successful broker submission to return HTTP 202 with status `submitted`, so that I can distinguish acceptance from validation and duplicate results.
31. As a script operator, I want rejected validation requests to return HTTP 400 with a reason, so that I can correct the order intent.
32. As a script operator, I want idempotency conflicts to return HTTP 409, so that key reuse with changed terms is distinguishable from a duplicate retry.
33. As a script operator, I want unknown submission outcomes to return HTTP 502, so that transport and native failures are not reported as accepted orders.
34. As a script operator, I want accepted orders to carry `broker_accepted: null`, so that the response does not claim broker acknowledgement before the order query can confirm it.
35. As a script operator, I want to query today's orders after submission, so that I can reconcile the actual order status.
36. As a script operator, I want to query today's deals through the native `DEAL` data type, so that filled trades are not silently reported as empty.
37. As a script operator, I want each deal to include the source order id and user order id, so that I can connect a fill to the submitted request.
38. As a script operator, I want each deal to include commission, so that transaction cost is available without another query.
39. As a script operator, I want a deal query failure to remain an error, so that an empty list is not confused with a successful query.
40. As a script operator, I want the generic API to reject `global.passorder`, so that the dedicated safety checks cannot be bypassed.
41. As a script operator, I want the generic API to reject `global.algo_passorder`, so that algorithmic submission cannot bypass the dedicated safety checks.
42. As a script operator, I want the generic API to reject `global.smart_algo_passorder`, so that smart algorithmic submission cannot bypass the dedicated safety checks.
43. As a script operator, I want the generic API to reject backtest order helpers in live mode, so that backtest-only APIs cannot create live orders.
44. As a script operator, I want generic cancellation to remain available, so that blocking order creation does not block order cancellation.
45. As a script operator, I want generic read-only trade queries to remain available, so that blocking order creation does not block reconciliation.
46. As a script operator, I want startup validation to reject an unknown trading safety key, so that a typo in `connection.json` cannot be ignored.
47. As a script operator, I want startup validation to require boolean `dry_run`, so that string or numeric values cannot enable a misleading preview mode.
48. As a script operator, I want startup validation to require a finite non-negative `max_order_amount`, so that NaN, infinity and negative caps are rejected.
49. As a script operator, I want bootstrap to add missing trading safety keys without replacing the connection file, so that the bridge secret, account and asset digests remain intact.
50. As a script operator, I want bootstrap to add `dry_run: false` and `max_order_amount: 500000` when those keys are missing, so that a legacy connection file receives the documented defaults.
51. As a script operator, I want bootstrap to preserve existing `dry_run` and `max_order_amount` values, so that a later deployment does not silently change a configured cap.
52. As a script operator, I want a second bootstrap run to report that the trading safety configuration already exists, so that the operation is visibly idempotent.
53. As a script operator, I want CLI buy and sell commands to pass dry-run and idempotency values to the bridge route, so that the command-line path has the same behavior as rpc and server.
54. As a script operator, I want CLI validation failures to return the stable JSON failure envelope, so that scripts can handle errors without parsing prose.
55. As a script operator, I want automated tests to avoid real orders, so that the safety suite can run without moving money.
56. As a script operator, I want to run the complete pytest suite and Ruff check after the implementation, so that the change is accepted only when the repository gates pass.

## Implementation Decisions

- The bridge route remains the only live order route. xtquant 直连 and native 路由 are not part of this feature.
- The bridge route submits one validated limit order at a time.
- A normalized order intent contains stock, side, volume, price, price type, user order id and startup-bound account.
- The dedicated buy and sell endpoints accept only `prType=11`. Other price types are rejected before `passorder`.
- The bridge rejects non-finite prices, non-positive limit prices, non-integer volumes and volumes that are not positive multiples of 100.
- The bridge obtains contract details from the full QMT context and uses the upper price limit, lower price limit and tick size to validate a limit price.
- Contract detail read failure, non-object detail, missing finite price limits or missing positive tick size rejects the order. The bridge does not degrade to cap-only validation.
- `max_order_amount` is read from the bridge startup configuration. A positive cap compares against the submitted limit price multiplied by volume. Zero disables the cap. Invalid configuration rejects strategy startup.
- `dry_run` is read from the bridge startup configuration and may also be requested by the HTTP body. Dry-run validates the intent and returns the normalized request without calling `passorder` and without reserving an idempotency key.
- Real submissions require a user order id. The bridge treats it as the idempotency key and scopes reservations by the startup-bound account.
- The bridge derives a stable fingerprint from the account and normalized order intent. The same idempotency key with a different fingerprint is a conflict.
- Duplicate lookup reads both today's orders and today's deals through the bridge route and matches the user order id in the order remark.
- Lookup failure blocks submission. A successful empty lookup is the only result that allows the duplicate check to continue.
- The bridge serializes lookup, reservation and submission per idempotency key for the lifetime of the bridge process.
- The bridge records a reservation before calling `passorder`. A repeated uncertain reservation reports the prior uncertainty and never resubmits.
- A native exception or uncertain transport result returns `outcome_unknown` with `retry_safe: false`. A negative native return code reports a failed submission.
- A successful native return reports HTTP 202 with `submitted` and `broker_accepted: null`. The caller reconciles the order through the order query.
- Reservations are process-local. Restart-safe exactly-once behavior is out of scope and must be documented.
- Completed duplicate replays return the existing order without requiring current cash, position or contract-detail validation.
- The generic API authorizes every trade-effect catalog entry before dispatch and rejects real order-creation entries. Cancellation and read-only trade queries remain available.
- Startup configuration validation rejects unknown keys, non-boolean `dry_run`, non-finite or negative `max_order_amount` and invalid trading safety values.
- Bootstrap adds missing trading safety keys through a merge that preserves the rest of the connection file. It does not replace the secret, account, endpoint or asset digests.
- The CLI buy and sell paths call the bridge route with the same normalized intent used by rpc and server. The CLI dry-run flag sets the request body field, and the CLI user order id sets the idempotency key.
- The response model distinguishes `submitted`, `duplicate`, `dry_run`, `rejected` and `outcome_unknown` states. These states are represented by explicit response fields rather than separate boolean flags.
- The HTTP error response uses the existing bridge JSON error shape. Validation errors use HTTP 400, idempotency conflicts use HTTP 409 and unknown submission outcomes use HTTP 502.
- The client `place_order` operation delegates duplicate lookup and submission to the bridge. It does not keep a second client-side idempotency cache.
- The order and deal converters preserve the native identifiers and fields required for reconciliation, including order id, user order id, price, volume, traded volume, deal id and commission.
- The implementation may add focused helpers inside the existing bridge and client modules. It must not add a second order service or a second transport.

## Testing Decisions

- Tests assert external behavior through the highest existing seam. They do not assert private helper calls or implementation-only counters.
- The primary test seam is the bridge HTTP boundary. Tests construct a bridge application with a fake QMT context and drive the buy, sell, order-status, trade-status and generic API routes.
- A good test proves a consumer-visible outcome. A rejected request must produce the documented HTTP status and JSON error without reaching the native submission function. A successful request must produce the documented response and native call arguments.
- The bridge HTTP tests cover valid limit orders, non-limit price types, malformed symbols, invalid prices, invalid volumes, upper and lower price limits, tick-grid rejection, missing contract detail, invalid configuration, amount-cap boundaries, dry-run validation, dry-run non-submission and dry-run reservation behavior.
- The bridge HTTP tests cover exact duplicate lookup, conflicting fingerprint, deal-only duplicate lookup, order-query failure, concurrent same-key requests, reservation-before-submit behavior, unknown native outcome and completed replay behavior.
- The generic API test uses a catalog containing every real order-creation entry and proves that each entry is rejected while cancellation and a read-only trade query remain authorized.
- The bootstrap configuration test uses a temporary connection file and proves that missing trading keys are added, existing keys are preserved, the rest of the file is unchanged and a second run reports no missing keys.
- The CLI tests use the existing fake bridge HTTP fixture to prove that buy, sell, dry-run and user-order-id values reach the request body without a real QMT process.
- The deal converter test uses native deal-shaped objects and asserts the external order id, user order id, price, volume, amount, commission and direction fields.
- Tests must not submit real orders, connect to a real broker account or require a running full QMT client.
- Prior art is the existing bridge API, market client and bootstrap tests. New tests follow their pytest fixture style and use fake QMT responses rather than live SDK objects.
- The final gate is `uv run --extra dev pytest -q` and `uv run --extra dev ruff check .`. Both commands must run successfully before delivery.

## Out of Scope

- Real buy or sell order submission during implementation or testing.
- Live sell verification. A successful buy does not prove that a sell can fill.
- T+1 settlement changes or broker-side position accounting.
- Market-order, algorithmic-order and smart-algorithmic-order support on the dedicated endpoints.
- Restart-persistent exactly-once idempotency or a durable reservation store.
- A new order service, a new broker adapter or a new transport.
- MCP write tools. The MCP tool surface remains read-only.
- Changes to xtquant 直连 or native 路由.
- A new issue tracker or triage vocabulary. The repository already defines `ready-for-agent`.
- A source baseline decision. The current implementation must first be synchronized to a current LayerFS branch because the active LayerFS project lacks `src/qmtcli/daqmt_market.py`.

## Further Notes

- The current active LayerFS project is `qmtcli-20261024`. Its `main@b58592e15fad` does not contain `src/qmtcli/daqmt_market.py`, and none of the 105 checked branches contained that file. The older `daqmt-auto-order-20261102` branch contains only an older deployed server and is not a valid substitute.
- The current local checkout contains uncommitted order-safety work in the bridge, client, CLI, bootstrap and tests. It has not been synchronized to LayerFS and is not accepted as the implementation baseline.
- The current bridge uses the dedicated buy and sell routes for `passorder` calls. The current client has a pre-submit order lookup, but it is not the final server-side reservation protocol.
- The current bridge `DEAL` query is the correct native trade data type. The prior `TRADE` value did not return deals.
- A limit buy that was verified in the live client does not validate the sell path. The current account position showed `can_use_volume=0` after the same-day buy.
- The specification must be implemented only after the current source is synchronized to the selected LayerFS branch. The implementation must preserve the existing bridge secret handling and must not print `connection.json` secrets.
- The expected seam count is two. The bridge HTTP boundary covers order behavior, and the bootstrap configuration result covers legacy configuration migration.