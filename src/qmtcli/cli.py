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


AGENT_CAPABILITIES: dict[str, Any] = {
    "protocol": "qmtcli.agent.v1",
    "transports": ["cli", "rpc", "server"],
    "commands": [
        {
            "name": "status",
            "rpc_command": "status",
            "description": "Check whether xtquant is importable.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"path": "optional QMT root or userdata_mini path"},
        },
        {
            "name": "doctor",
            "rpc_command": "doctor",
            "description": "Return SDK/module/path diagnostics.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"path": "optional", "account": "optional"},
        },
        {
            "name": "data_call",
            "cli_command": "data-call",
            "description": "Call a public xtquant.xtdata method.",
            "requires_account": False,
            "danger": "escape_hatch",
            "inputs": {"method": "required", "args": "optional array", "kwargs": "optional object"},
        },
        {
            "name": "download",
            "description": "Call an xtdata download_* function to populate the local QMT cache.",
            "requires_account": False,
            "danger": "downloads_data",
            "inputs": {
                "target": (
                    "required, one of history, financials, sectors, index-weight, cb, etf, "
                    "holidays, history-contracts"
                ),
                "symbols": "required for the history and financials targets",
            },
        },
        {
            "name": "calendar",
            "description": "Call xtdata.get_trading_calendar.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {
                "market": "required, for example SH or SZ",
                "start": "optional start_time",
                "end": "optional end_time",
            },
        },
        {
            "name": "sector-list",
            "description": "Call xtdata.get_sector_list.",
            "requires_account": False,
            "danger": "safe",
        },
        {
            "name": "sector-stocks",
            "description": "Call xtdata.get_stock_list_in_sector.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"sector": "required sector name, for example 沪深A股"},
        },
        {
            "name": "full-tick",
            "description": "Call xtdata.get_full_tick.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"symbols": "one or more symbols"},
        },
        {
            "name": "bars",
            "description": "Call xtdata.get_market_data_ex.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {
                "symbols": "one or more symbols",
                "fields": "optional field list",
                "period": "default 1d",
                "start": "optional start_time",
                "end": "optional end_time",
                "count": "default -1",
                "dividend_type": "default none",
                "fill_data": "default true; pass --no-fill-data to disable",
            },
        },
        {
            "name": "l2-quote",
            "description": "Call xtdata.get_l2_quote.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {
                "symbol": "required single symbol",
                "fields": "optional field list",
                "start": "optional start_time",
                "end": "optional end_time",
                "count": "default -1",
            },
            "note": "requires Level-2 data permission; not covered by the public xtdata doc page",
        },
        {
            "name": "l2-order",
            "description": "Call xtdata.get_l2_order.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {
                "symbol": "required single symbol",
                "fields": "optional field list",
                "start": "optional start_time",
                "end": "optional end_time",
                "count": "default -1",
            },
            "note": "requires Level-2 data permission; not covered by the public xtdata doc page",
        },
        {
            "name": "l2-transaction",
            "description": "Call xtdata.get_l2_transaction.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {
                "symbol": "required single symbol",
                "fields": "optional field list",
                "start": "optional start_time",
                "end": "optional end_time",
                "count": "default -1",
            },
            "note": "requires Level-2 data permission; not covered by the public xtdata doc page",
        },
        {
            "name": "instrument-detail",
            "description": "Call xtdata.get_instrument_detail.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"symbol": "required", "complete": "optional, default false"},
        },
        {
            "name": "instrument-type",
            "description": "Call xtdata.get_instrument_type.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"symbol": "required"},
        },
        {
            "name": "trading-dates",
            "description": "Call xtdata.get_trading_dates.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {
                "market": "required, for example SH or SZ",
                "start": "optional start_time",
                "end": "optional end_time",
                "count": "default -1",
            },
        },
        {
            "name": "divid-factors",
            "description": "Call xtdata.get_divid_factors.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"symbol": "required", "start": "optional start_time", "end": "optional end_time"},
        },
        {
            "name": "holidays",
            "description": "Call xtdata.get_holidays.",
            "requires_account": False,
            "danger": "safe",
        },
        {
            "name": "period-list",
            "description": "Call xtdata.get_period_list.",
            "requires_account": False,
            "danger": "safe",
        },
        {
            "name": "ipo-info",
            "description": "Call xtdata.get_ipo_info.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"start": "optional start_time", "end": "optional end_time"},
        },
        {
            "name": "cb-info",
            "description": "Call xtdata.get_cb_info.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"symbol": "required convertible bond code, for example 123001.SZ"},
        },
        {
            "name": "etf-info",
            "description": "Call xtdata.get_etf_info.",
            "requires_account": False,
            "danger": "safe",
        },
        {
            "name": "index-weight",
            "description": "Call xtdata.get_index_weight.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {"index_code": "required, for example 000300.SH"},
        },
        {
            "name": "financials",
            "description": "Call xtdata.get_financial_data.",
            "requires_account": False,
            "danger": "safe",
            "inputs": {
                "symbols": "one or more symbols",
                "tables": "optional financial table list",
                "start": "optional start_time",
                "end": "optional end_time",
                "report_type": "default report_time",
            },
        },
        {
            "name": "asset",
            "description": "Query account asset.",
            "requires_account": True,
            "danger": "safe",
        },
        {
            "name": "positions",
            "description": "Query account positions.",
            "requires_account": True,
            "danger": "safe",
        },
        {
            "name": "orders",
            "description": "Query account orders.",
            "requires_account": True,
            "danger": "safe",
        },
        {
            "name": "trades",
            "description": "Query account trades.",
            "requires_account": True,
            "danger": "safe",
        },
        {
            "name": "buy",
            "description": "Submit a fixed-price stock buy order.",
            "requires_account": True,
            "danger": "places_order",
            "inputs": {"symbol": "required", "volume": "positive multiple of 100", "price": "positive"},
        },
        {
            "name": "sell",
            "description": "Submit a fixed-price stock sell order.",
            "requires_account": True,
            "danger": "places_order",
            "inputs": {"symbol": "required", "volume": "positive multiple of 100", "price": "positive"},
        },
        {
            "name": "cancel",
            "description": "Cancel an order by QMT order id.",
            "requires_account": True,
            "danger": "cancels_order",
            "inputs": {"order_id": "required"},
        },
        {
            "name": "trade_call",
            "cli_command": "trade-call",
            "description": "Call a public XtQuantTrader method.",
            "requires_account": True,
            "danger": "escape_hatch",
            "inputs": {
                "method": "required",
                "args": "optional array",
                "kwargs": "optional object",
                "with_account": "default true",
            },
        },
    ],
}

AGENT_SCHEMA: dict[str, Any] = {
    "protocol": "qmtcli.agent.v1",
    "request": {
        "id": "optional string or number; echoed when present",
        "command": "required string",
        "path": "optional QMT root or userdata_mini path",
        "account": "required for account/trade commands",
        "account_type": "optional, default STOCK",
    },
    "response": {
        "ok": "boolean",
        "data": "present on success",
        "error": "present on failure",
        "id": "echoed when request id exists",
    },
    "server": {
        "transport": "stdin/stdout JSONL",
        "network": False,
        "line_contract": "one JSON request per input line, one JSON response per output line",
    },
    "danger_levels": {
        "safe": "read-only or local diagnostics",
        "escape_hatch": "calls a public SDK method selected by the caller",
        "downloads_data": "downloads data into the local QMT cache",
        "places_order": "submits a broker order",
        "cancels_order": "cancels a broker order",
    },
}

AGENT_EXAMPLES: dict[str, Any] = {
    "status": {"command": "status"},
    "doctor": {"command": "doctor", "path": "D:\\DFZQxtqmt_client_real_win64\\userdata_mini"},
    "data_call": {
        "command": "data_call",
        "method": "get_stock_list_in_sector",
        "args": ["沪深A股"],
        "kwargs": {},
    },
    "buy": {
        "command": "buy",
        "path": "D:\\DFZQxtqmt_client_real_win64\\userdata_mini",
        "account": "ACCOUNT_ID",
        "account_type": "STOCK",
        "symbol": "600519.SH",
        "volume": 100,
        "price": 1500.0,
    },
}


def _agent_response(data: Any) -> dict[str, Any]:
    return {"ok": True, "data": data}


def _parser(description: str, **kwargs: Any) -> argparse.ArgumentParser:
    return argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        **kwargs,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _parser(
        "Local QMT/XtQuant command line bridge.\n"
        "All commands talk to the local broker QMT installation; qmtcli does not download QMT.",
    )
    parser.add_argument("--path", help="QMT install root or userdata_mini path")
    parser.add_argument("--account", help="QMT account id; required by trade/account commands")
    parser.add_argument("--account-type", default="STOCK", help="QMT account type, default: STOCK")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("capabilities", help="print agent-readable capability metadata")
    subparsers.add_parser("schema", help="print agent-readable RPC/server schema")
    subparsers.add_parser("examples", help="print built-in agent request examples")
    subparsers.add_parser("status", help="check whether xtquant is importable")
    subparsers.add_parser("doctor", help="show SDK/module/path diagnostics")
    subparsers.add_parser("asset", help="query stock asset for --account")
    subparsers.add_parser("positions", help="query positions for --account")
    subparsers.add_parser("orders", help="query orders for --account")
    subparsers.add_parser("trades", help="query trades for --account")
    calendar = subparsers.add_parser(
        "calendar",
        help="call xtdata.get_trading_calendar",
        description="Return trading calendar days for a market via xtdata.get_trading_calendar.",
    )
    calendar.add_argument("market", help="Market such as SH, SZ")
    calendar.add_argument("--start", default="", help="Start date YYYYMMDD; default: ''")
    calendar.add_argument("--end", default="", help="End date YYYYMMDD; default: ''")

    subparsers.add_parser("sector-list", help="call xtdata.get_sector_list")

    sector_stocks = subparsers.add_parser(
        "sector-stocks",
        help="call xtdata.get_stock_list_in_sector",
        description="Return stocks in an xtdata sector, for example: 沪深A股.",
    )
    sector_stocks.add_argument("sector", help="Sector name, for example: 沪深A股")

    full_tick = subparsers.add_parser(
        "full-tick",
        help="call xtdata.get_full_tick",
        description="Return latest full-tick data for one or more symbols.",
    )
    full_tick.add_argument("symbols", nargs="+", help="Symbols such as 600519.SH 000001.SZ")

    bars = subparsers.add_parser(
        "bars",
        help="call xtdata.get_market_data_ex",
        description="Return historical bars via xtdata.get_market_data_ex.",
    )
    bars.add_argument("symbols", nargs="+", help="Symbols such as 600519.SH")
    bars.add_argument("--fields", nargs="*", default=[], help="Field list; default: all fields")
    bars.add_argument("--period", default="1d", help="Period such as 1d, 1m, 5m; default: 1d")
    bars.add_argument("--start", default="", help="Start time; default: ''")
    bars.add_argument("--end", default="", help="End time; default: ''")
    bars.add_argument("--count", default=-1, type=int, help="Bar count; default: -1")
    bars.add_argument(
        "--dividend-type",
        default="none",
        help="Dividend type: none, front, back, front_ratio, back_ratio; default: none",
    )
    bars.add_argument(
        "--no-fill-data",
        action="store_true",
        help="Disable forward-filling of missing bars (fill_data=False)",
    )

    l2_quote = subparsers.add_parser(
        "l2-quote",
        help="call xtdata.get_l2_quote",
        description=(
            "Return Level-2 quote snapshots for a single symbol via xtdata.get_l2_quote.\n"
            "Requires Level-2 data permission; not covered by the public xtdata doc page."
        ),
    )
    l2_quote.add_argument("symbol", help="Symbol such as 600519.SH")
    l2_quote.add_argument("--fields", nargs="*", default=[], help="Field list; default: all fields")
    l2_quote.add_argument("--start", default="", help="Start time; default: ''")
    l2_quote.add_argument("--end", default="", help="End time; default: ''")
    l2_quote.add_argument("--count", default=-1, type=int, help="Count; default: -1")

    l2_order = subparsers.add_parser(
        "l2-order",
        help="call xtdata.get_l2_order",
        description=(
            "Return Level-2 order queue data for a single symbol via xtdata.get_l2_order.\n"
            "Requires Level-2 data permission; not covered by the public xtdata doc page."
        ),
    )
    l2_order.add_argument("symbol", help="Symbol such as 600519.SH")
    l2_order.add_argument("--fields", nargs="*", default=[], help="Field list; default: all fields")
    l2_order.add_argument("--start", default="", help="Start time; default: ''")
    l2_order.add_argument("--end", default="", help="End time; default: ''")
    l2_order.add_argument("--count", default=-1, type=int, help="Count; default: -1")

    l2_transaction = subparsers.add_parser(
        "l2-transaction",
        help="call xtdata.get_l2_transaction",
        description=(
            "Return Level-2 transaction data for a single symbol via xtdata.get_l2_transaction.\n"
            "Requires Level-2 data permission; not covered by the public xtdata doc page."
        ),
    )
    l2_transaction.add_argument("symbol", help="Symbol such as 600519.SH")
    l2_transaction.add_argument("--fields", nargs="*", default=[], help="Field list; default: all fields")
    l2_transaction.add_argument("--start", default="", help="Start time; default: ''")
    l2_transaction.add_argument("--end", default="", help="End time; default: ''")
    l2_transaction.add_argument("--count", default=-1, type=int, help="Count; default: -1")

    instrument_detail = subparsers.add_parser(
        "instrument-detail",
        help="call xtdata.get_instrument_detail",
    )
    instrument_detail.add_argument("symbol", help="Symbol such as 600519.SH")
    instrument_detail.add_argument(
        "--complete",
        action="store_true",
        help="Return the complete instrument detail field set",
    )

    instrument_type = subparsers.add_parser(
        "instrument-type",
        help="call xtdata.get_instrument_type",
    )
    instrument_type.add_argument("symbol", help="Symbol such as 600519.SH")

    trading_dates = subparsers.add_parser(
        "trading-dates",
        help="call xtdata.get_trading_dates",
    )
    trading_dates.add_argument("market", help="Market such as SH, SZ")
    trading_dates.add_argument("--start", default="", help="Start date YYYYMMDD; default: ''")
    trading_dates.add_argument("--end", default="", help="End date YYYYMMDD; default: ''")
    trading_dates.add_argument("--count", default=-1, type=int, help="Date count; default: -1")

    divid_factors = subparsers.add_parser(
        "divid-factors",
        help="call xtdata.get_divid_factors",
    )
    divid_factors.add_argument("symbol", help="Symbol such as 600519.SH")
    divid_factors.add_argument("--start", default="", help="Start time; default: ''")
    divid_factors.add_argument("--end", default="", help="End time; default: ''")

    subparsers.add_parser("holidays", help="call xtdata.get_holidays")
    subparsers.add_parser("period-list", help="call xtdata.get_period_list")

    ipo_info = subparsers.add_parser("ipo-info", help="call xtdata.get_ipo_info")
    ipo_info.add_argument("--start", default="", help="Start time; default: ''")
    ipo_info.add_argument("--end", default="", help="End time; default: ''")

    cb_info = subparsers.add_parser("cb-info", help="call xtdata.get_cb_info")
    cb_info.add_argument("symbol", help="Convertible bond code such as 123001.SZ")

    subparsers.add_parser("etf-info", help="call xtdata.get_etf_info")

    index_weight = subparsers.add_parser("index-weight", help="call xtdata.get_index_weight")
    index_weight.add_argument("index_code", help="Index code such as 000300.SH")

    financials = subparsers.add_parser(
        "financials",
        help="call xtdata.get_financial_data",
    )
    financials.add_argument("symbols", nargs="+", help="Symbols such as 600519.SH")
    financials.add_argument(
        "--tables",
        nargs="*",
        default=[],
        help="Financial table names such as Balance, Income; default: all tables",
    )
    financials.add_argument("--start", default="", help="Start time; default: ''")
    financials.add_argument("--end", default="", help="End time; default: ''")
    financials.add_argument(
        "--report-type",
        default="report_time",
        help="report_time or announce_time; default: report_time",
    )

    download = subparsers.add_parser(
        "download",
        help="call an xtdata download_* function to populate the local QMT cache",
        description=(
            "Download data into the local QMT cache via xtdata download_* functions.\n"
            "target: history, financials, sectors, index-weight, cb, etf, holidays, "
            "history-contracts.\n"
            "symbols are required for the history and financials targets.\n\n"
            "Example:\n"
            "  qmtcli download history 600519.SH --period 1d"
        ),
    )
    download.add_argument(
        "target",
        choices=[
            "history",
            "financials",
            "sectors",
            "index-weight",
            "cb",
            "etf",
            "holidays",
            "history-contracts",
        ],
        help="What to download",
    )
    download.add_argument(
        "symbols",
        nargs="*",
        help="Symbols; required for the history and financials targets",
    )
    download.add_argument("--period", default="1d", help="Period for the history target; default: 1d")
    download.add_argument("--start", default="", help="Start time; default: ''")
    download.add_argument("--end", default="", help="End time; default: ''")
    download.add_argument(
        "--incrementally",
        action="store_true",
        help="For the history target, only download data since the last local update",
    )
    download.add_argument(
        "--tables",
        nargs="*",
        default=[],
        help="Financial table names for the financials target; default: all tables",
    )

    data_call = subparsers.add_parser(
        "data-call",
        help="call an arbitrary public xtquant.xtdata method",
        description=(
            "Call an arbitrary public xtquant.xtdata method.\n"
            "Private methods beginning with '_' are blocked.\n\n"
            "Example:\n"
            "  qmtcli data-call get_stock_list_in_sector --args '[\"沪深A股\"]'"
        ),
    )
    data_call.add_argument("method", help="Public xtdata method name")
    data_call.add_argument("--args", default="[]", help="JSON positional args array; default: []")
    data_call.add_argument("--kwargs", default="{}", help="JSON keyword args object; default: {}")

    trade_call = subparsers.add_parser(
        "trade-call",
        help="call an arbitrary public XtQuantTrader method",
        description=(
            "Call an arbitrary public XtQuantTrader method after connecting --account.\n"
            "By default the StockAccount object is prepended to args; pass --no-account to skip it.\n"
            "Private methods beginning with '_' are blocked."
        ),
    )
    trade_call.add_argument("method", help="Public XtQuantTrader method name")
    trade_call.add_argument("--args", default="[]", help="JSON positional args array; default: []")
    trade_call.add_argument("--kwargs", default="{}", help="JSON keyword args object; default: {}")
    trade_call.add_argument("--no-account", action="store_true", help="Do not prepend StockAccount")

    buy = subparsers.add_parser("buy", help="submit a fixed-price stock buy order")
    buy.add_argument("symbol", help="Symbol such as 600519.SH")
    buy.add_argument("volume", type=int, help="A-share volume; must be a positive multiple of 100")
    buy.add_argument("price", type=float, help="Limit price; must be positive")

    sell = subparsers.add_parser("sell", help="submit a fixed-price stock sell order")
    sell.add_argument("symbol", help="Symbol such as 600519.SH")
    sell.add_argument("volume", type=int, help="A-share volume; must be a positive multiple of 100")
    sell.add_argument("price", type=float, help="Limit price; must be positive")

    cancel = subparsers.add_parser("cancel", help="cancel an order by QMT order id")
    cancel.add_argument("order_id", help="QMT order id")

    subparsers.add_parser(
        "rpc",
        help="handle one JSON request from stdin and print one JSON response",
        description=(
            "Read one JSON request from stdin and write one JSON response.\n"
            "Supported commands include status, doctor, data_call, asset, positions, orders,\n"
            "trades, buy, sell, cancel, and trade_call."
        ),
    )
    subparsers.add_parser(
        "server",
        help="run a stdin/stdout JSONL request loop",
        description=(
            "Read newline-delimited JSON requests from stdin and print one JSON response per line.\n"
            "This is a local automation loop, not a TCP server."
        ),
    )
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
    if args.command == "capabilities":
        _print_json(_agent_response(AGENT_CAPABILITIES))
        return 0
    if args.command == "schema":
        _print_json(_agent_response(AGENT_SCHEMA))
        return 0
    if args.command == "examples":
        _print_json(_agent_response(AGENT_EXAMPLES))
        return 0
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
        "instrument-detail",
        "instrument-type",
        "trading-dates",
        "divid-factors",
        "holidays",
        "period-list",
        "ipo-info",
        "cb-info",
        "etf-info",
        "index-weight",
        "financials",
        "download",
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
        _print_json(
            gateway.call_trader(
                args.method,
                *json.loads(args.args),
                with_account=not args.no_account,
                **json.loads(args.kwargs),
            )
        )
    return 0


def _handle_data_command(args: argparse.Namespace) -> Any:
    if args.command == "calendar":
        return QMTGateway.call_data(
            "get_trading_calendar",
            args.market,
            start_time=args.start,
            end_time=args.end,
        )
    if args.command == "sector-list":
        return QMTGateway.call_data("get_sector_list")
    if args.command == "sector-stocks":
        return QMTGateway.call_data("get_stock_list_in_sector", args.sector)
    if args.command == "full-tick":
        return QMTGateway.call_data("get_full_tick", args.symbols)
    if args.command == "bars":
        return QMTGateway.call_data(
            "get_market_data_ex",
            args.fields,
            args.symbols,
            period=args.period,
            start_time=args.start,
            end_time=args.end,
            count=args.count,
            dividend_type=args.dividend_type,
            fill_data=not args.no_fill_data,
        )
    if args.command == "l2-quote":
        return QMTGateway.call_data(
            "get_l2_quote",
            args.fields,
            args.symbol,
            start_time=args.start,
            end_time=args.end,
            count=args.count,
        )
    if args.command == "l2-order":
        return QMTGateway.call_data(
            "get_l2_order",
            args.fields,
            args.symbol,
            start_time=args.start,
            end_time=args.end,
            count=args.count,
        )
    if args.command == "l2-transaction":
        return QMTGateway.call_data(
            "get_l2_transaction",
            args.fields,
            args.symbol,
            start_time=args.start,
            end_time=args.end,
            count=args.count,
        )
    if args.command == "instrument-detail":
        return QMTGateway.call_data("get_instrument_detail", args.symbol, args.complete)
    if args.command == "instrument-type":
        return QMTGateway.call_data("get_instrument_type", args.symbol)
    if args.command == "trading-dates":
        return QMTGateway.call_data(
            "get_trading_dates",
            args.market,
            start_time=args.start,
            end_time=args.end,
            count=args.count,
        )
    if args.command == "divid-factors":
        return QMTGateway.call_data(
            "get_divid_factors",
            args.symbol,
            start_time=args.start,
            end_time=args.end,
        )
    if args.command == "holidays":
        return QMTGateway.call_data("get_holidays")
    if args.command == "period-list":
        return QMTGateway.call_data("get_period_list")
    if args.command == "ipo-info":
        return QMTGateway.call_data("get_ipo_info", start_time=args.start, end_time=args.end)
    if args.command == "cb-info":
        return QMTGateway.call_data("get_cb_info", args.symbol)
    if args.command == "etf-info":
        return QMTGateway.call_data("get_etf_info")
    if args.command == "index-weight":
        return QMTGateway.call_data("get_index_weight", args.index_code)
    if args.command == "financials":
        return QMTGateway.call_data(
            "get_financial_data",
            args.symbols,
            table_list=args.tables,
            start_time=args.start,
            end_time=args.end,
            report_type=args.report_type,
        )
    if args.command == "data-call":
        return QMTGateway.call_data(args.method, *json.loads(args.args), **json.loads(args.kwargs))
    if args.command == "download":
        return _handle_download_command(args)
    raise ValueError(f"unknown data command: {args.command}")


def _handle_download_command(args: argparse.Namespace) -> Any:
    target = args.target
    if target == "history":
        if not args.symbols:
            raise SystemExit("download history requires one or more symbols")
        QMTGateway.call_data(
            "download_history_data2",
            args.symbols,
            args.period,
            start_time=args.start,
            end_time=args.end,
            incrementally=True if args.incrementally else None,
        )
    elif target == "financials":
        if not args.symbols:
            raise SystemExit("download financials requires one or more symbols")
        QMTGateway.call_data("download_financial_data", args.symbols, table_list=args.tables)
    elif target == "sectors":
        QMTGateway.call_data("download_sector_data")
    elif target == "index-weight":
        QMTGateway.call_data("download_index_weight")
    elif target == "cb":
        QMTGateway.call_data("download_cb_data")
    elif target == "etf":
        QMTGateway.call_data("download_etf_info")
    elif target == "holidays":
        QMTGateway.call_data("download_holiday_data")
    elif target == "history-contracts":
        QMTGateway.call_data("download_history_contracts")
    else:
        raise ValueError(f"unknown download target: {target}")
    return {"ok": True, "downloaded": target, "symbols": args.symbols}


def _handle_rpc_request(request: dict[str, Any]) -> dict[str, Any]:
    request_id = request.get("id")
    try:
        data = _handle_rpc_data(request)
    except Exception as exc:  # noqa: BLE001 - JSON RPC boundary must report arbitrary failures.
        response = {"ok": False, "error": str(exc)}
    else:
        response = {"ok": True, "data": data}
    if request_id is not None:
        response["id"] = request_id
    return response


def _handle_rpc_data(request: dict[str, Any]) -> Any:
    command = request.get("command")
    if command == "capabilities":
        return AGENT_CAPABILITIES
    if command == "schema":
        return AGENT_SCHEMA
    if command == "examples":
        return AGENT_EXAMPLES
    if command == "status":
        return {"xtquant": QMTGateway.is_available(request.get("path"))}
    if command == "doctor":
        return QMTGateway.sdk_diagnostics(request.get("path"), request.get("account"))
    if command == "data_call":
        return QMTGateway.call_data(
            request["method"],
            *request.get("args", []),
            **request.get("kwargs", {}),
        )

    account_commands = {
        "asset",
        "positions",
        "orders",
        "trades",
        "buy",
        "sell",
        "cancel",
        "trade_call",
    }
    if command not in account_commands:
        raise ValueError(f"unknown command: {command}")

    gateway = QMTGateway(
        QMTConnection(
            request.get("path", ""),
            request.get("account", ""),
            request.get("account_type", "STOCK"),
        )
    )
    gateway.connect()
    if command == "asset":
        return gateway.query_asset()
    if command == "positions":
        return gateway.query_positions()
    if command == "orders":
        return gateway.query_orders()
    if command == "trades":
        return gateway.query_trades()
    if command == "buy":
        return gateway.submit_order(request["symbol"], "BUY", request["volume"], request["price"])
    if command == "sell":
        return gateway.submit_order(request["symbol"], "SELL", request["volume"], request["price"])
    if command == "cancel":
        return gateway.cancel_order(request["order_id"])
    if command == "trade_call":
        return gateway.call_trader(
            request["method"],
            *request.get("args", []),
            with_account=request.get("with_account", True),
            **request.get("kwargs", {}),
        )


def _rpc() -> int:
    request = json.loads((sys.stdin.read() or "{}").lstrip("\ufeff"))
    print(json.dumps(_handle_rpc_request(request), ensure_ascii=False, default=_json_default, indent=2))
    return 0


def _server() -> int:
    for line in sys.stdin:
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        response = _handle_rpc_request(json.loads(line))
        print(json.dumps(response, ensure_ascii=False, default=_json_default), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
