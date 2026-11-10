"""Read-only watch of the loopback QMT bridge: cash, holdings, and live ticks.

Only GET endpoints are used. Nothing here can place or cancel an order.
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

CONNECTION = Path.home() / "AppData/Local/QmtCli/daqmt/connection.json"


def get(config, path):
    request = urllib.request.Request(
        config["endpoint"] + path,
        headers={"X-Bridge-Secret": config["secret"]},
    )
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310 - loopback
        return json.loads(response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", default=[], help="tick symbols beyond holdings")
    parser.add_argument("--connection", type=Path, default=CONNECTION)
    args = parser.parse_args()

    if not args.connection.is_file():
        print(f"connection file missing: {args.connection}", file=sys.stderr)
        return 1
    config = json.loads(args.connection.read_text(encoding="utf-8"))

    try:
        health = get(config, "/api/health")
        money = get(config, "/api/money/available")
        holding = get(config, "/api/holding")
    except OSError as exc:
        print(f"bridge unreachable: {exc}", file=sys.stderr)
        return 1

    running = health.get("bridge_running")
    trading = health.get("trading_enabled")
    print(f"bridge_running={running} trading_enabled={trading}")
    print(f"available_money={money.get('available_money')}")
    print()
    print("| 代码 | 名称 | 持仓 | 可用 | 现价 | 市值 | 盈亏率 | 行情时点 |")
    print("|---|---|---|---|---|---|---|---|")

    symbols = list(holding) + [s for s in args.symbols if s not in holding]
    for symbol in symbols:
        position = holding.get(symbol, {})
        try:
            tick = get(config, f"/api/market/tick?symbol={symbol}").get("tick", {})
        except OSError:
            tick = {}
        print(
            f"| {symbol} | {position.get('instrument_name', '')} "
            f"| {position.get('volume', '')} | {position.get('can_use_volume', '')} "
            f"| {tick.get('lastPrice', '')} | {position.get('market_value', '')} "
            f"| {position.get('profit_rate', '')} | {tick.get('timetag', '')} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
