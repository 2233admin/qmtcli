"""Command line entry point for QMT/XtQuant."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, is_dataclass
from typing import Any

from qmtcli.gateway import QMTConnection, QMTGateway


def _json_default(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, default=_json_default, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QMT/XtQuant CLI")
    parser.add_argument("--path", help="miniQMT userdata_mini path or QMT install root")
    parser.add_argument("--account", help="QMT account id")
    parser.add_argument("--account-type", default="STOCK", help="QMT account type")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status", help="Check whether xtquant can be imported")
    subparsers.add_parser("doctor", help="Check QMT SDK support")
    subparsers.add_parser("asset", help="Query account asset")
    subparsers.add_parser("positions", help="Query positions")
    subparsers.add_parser("orders", help="Query orders")
    subparsers.add_parser("trades", help="Query trades")
    subparsers.add_parser("calendar", help="Query trading calendar")
    subparsers.add_parser("sector-list", help="Query sector list")

    sector_stocks = subparsers.add_parser("sector-stocks", help="Query stocks in a sector")
    sector_stocks.add_argument("sector", help="Sector name")

    full_tick = subparsers.add_parser("full-tick", help="Query full tick")
    full_tick.add_argument("symbols", nargs="+", help="Stock symbols")

    bars = subparsers.add_parser("bars", help="Query market bars")
    bars.add_argument("symbols", nargs="+", help="Stock symbols")
    bars.add_argument("--period", default="1d", help="Period, e.g. 1d/1m/5m")
    bars.add_argument("--count", type=int, default=-1, help="Bar count")

    l2_quote = subparsers.add_parser("l2-quote", help="Query L2 quote")
    l2_quote.add_argument("symbols", nargs="+", help="Stock symbols")

    l2_order = subparsers.add_parser("l2-order", help="Query L2 orders")
    l2_order.add_argument("symbol", help="Stock symbol")

    l2_transaction = subparsers.add_parser("l2-transaction", help="Query L2 transactions")
    l2_transaction.add_argument("symbol", help="Stock symbol")

    data_call = subparsers.add_parser("data-call", help="Call any xtdata function")
    data_call.add_argument("method", help="xtdata method name")
    data_call.add_argument("--args", default="[]", help="JSON array positional args")
    data_call.add_argument("--kwargs", default="{}", help="JSON object keyword args")

    trade_call = subparsers.add_parser("trade-call", help="Call any XtQuantTrader method")
    trade_call.add_argument("method", help="XtQuantTrader method name")
    trade_call.add_argument("--args", default="[]", help="JSON array positional args")
    trade_call.add_argument("--kwargs", default="{}", help="JSON object keyword args")
    trade_call.add_argument("--no-account", action="store_true", help="Do not prepend StockAccount")

    buy = subparsers.add_parser("buy", help="Submit a buy order")
    buy.add_argument("symbol", help="Stock symbol, e.g. 600519.SH")
    buy.add_argument("volume", type=int, help="Order volume")
    buy.add_argument("price", type=float, help="Limit price")

    sell = subparsers.add_parser("sell", help="Submit a sell order")
    sell.add_argument("symbol", help="Stock symbol, e.g. 600519.SH")
    sell.add_argument("volume", type=int, help="Order volume")
    sell.add_argument("price", type=float, help="Limit price")

    cancel = subparsers.add_parser("cancel", help="Cancel an order")
    cancel.add_argument("order_id", help="QMT order id")

    subparsers.add_parser("rpc", help="Read one JSON request from stdin and write one JSON response")
    subparsers.add_parser("server", help="Run a JSONL stdio server")
    return parser


def _connect(args: argparse.Namespace) -> QMTGateway:
    if not args.account:
        raise SystemExit("--account is required for this command")
    gateway = QMTGateway(QMTConnection(args.path or "", args.account, args.account_type))
    gateway.connect()
    return gateway


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "rpc":
        return _rpc()
    if args.command == "server":
        return _server()

    if args.command == "status":
        _print_json({"xtquant": QMTGateway.is_available(args.path)})
        return 0

    if args.command == "doctor":
        _print_json(QMTGateway.sdk_diagnostics(args.path, args.account))
        return 0

    if args.command in {
        "calendar",
        "sector-list",
        "sector-stocks",
        "full-tick",
        "bars",
        "l2-quote",
        "l2-order",
        "l2-transaction",
        "data-call",
    }:
        _print_json(_handle_data_command(args))
        return 0

    gateway = _connect(args)
    if args.command == "asset":
        _print_json(gateway.query_asset())
    elif args.command == "positions":
        _print_json(gateway.query_positions())
    elif args.command == "orders":
        _print_json(gateway.query_orders())
    elif args.command == "trades":
        _print_json(gateway.query_trades())
    elif args.command == "buy":
        _print_json(gateway.submit_order(args.symbol, "BUY", args.volume, args.price))
    elif args.command == "sell":
        _print_json(gateway.submit_order(args.symbol, "SELL", args.volume, args.price))
    elif args.command == "cancel":
        _print_json(gateway.cancel_order(args.order_id))
    elif args.command == "trade-call":
        call_args = json.loads(args.args)
        call_kwargs = json.loads(args.kwargs)
        _print_json(
            gateway.call_trader(
                args.method,
                *call_args,
                with_account=not args.no_account,
                **call_kwargs,
            )
        )
    return 0


def _handle_data_command(args: argparse.Namespace) -> Any:
    if args.command == "calendar":
        return QMTGateway.call_data("get_trading_calendar")
    if args.command == "sector-list":
        return QMTGateway.call_data("get_sector_list")
    if args.command == "sector-stocks":
        return QMTGateway.call_data("get_stock_list_in_sector", args.sector)
    if args.command == "full-tick":
        return QMTGateway.call_data("get_full_tick", args.symbols)
    if args.command == "bars":
        return QMTGateway.call_data(
            "get_market_data_ex",
            [],
            args.symbols,
            period=args.period,
            count=args.count,
        )
    if args.command == "l2-quote":
        return QMTGateway.call_data("get_l2_quote", args.symbols)
    if args.command == "l2-order":
        return QMTGateway.call_data("get_l2_order", args.symbol)
    if args.command == "l2-transaction":
        return QMTGateway.call_data("get_l2_transaction", args.symbol)
    if args.command == "data-call":
        return QMTGateway.call_data(args.method, *json.loads(args.args), **json.loads(args.kwargs))
    raise ValueError(f"unknown data command: {args.command}")


def _handle_rpc_request(request: dict[str, Any]) -> dict[str, Any]:
    command = request.get("command")
    if command == "status":
        return {"ok": True, "data": {"xtquant": QMTGateway.is_available(request.get("path"))}}
    if command == "doctor":
        return {
            "ok": True,
            "data": QMTGateway.sdk_diagnostics(request.get("path"), request.get("account")),
        }
    if command == "data_call":
        data = QMTGateway.call_data(
            request["method"],
            *request.get("args", []),
            **request.get("kwargs", {}),
        )
        return {"ok": True, "data": data}

    gateway = QMTGateway(
        QMTConnection(
            request.get("path", ""),
            request.get("account", ""),
            request.get("account_type", "STOCK"),
        )
    )
    gateway.connect()
    if command == "asset":
        data = gateway.query_asset()
    elif command == "positions":
        data = gateway.query_positions()
    elif command == "orders":
        data = gateway.query_orders()
    elif command == "trades":
        data = gateway.query_trades()
    elif command == "cancel":
        data = gateway.cancel_order(request["order_id"])
    elif command == "trade_call":
        data = gateway.call_trader(
            request["method"],
            *request.get("args", []),
            with_account=request.get("with_account", True),
            **request.get("kwargs", {}),
        )
    elif command == "order":
        data = gateway.submit_order(
            request["symbol"],
            request["side"],
            int(request["volume"]),
            float(request["price"]),
        )
    else:
        raise ValueError(f"unknown command: {command}")
    return {"ok": True, "data": data}


def _rpc() -> int:
    try:
        request = json.loads((sys.stdin.read() or "{}").lstrip("\ufeff"))
        response = _handle_rpc_request(request)
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}

    _print_json(response)
    return 0


def _server() -> int:
    for line in sys.stdin:
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        try:
            request = json.loads(line)
            response = _handle_rpc_request(request)
            if "id" in request:
                response["id"] = request["id"]
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        print(json.dumps(response, ensure_ascii=False, default=_json_default), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
