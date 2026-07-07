"""Table-driven coverage of CLI data/download commands against xtdata call_data dispatch.

These tests assert the exact xtdata method name plus positional/keyword argument mapping used by
every named data command, so a signature drift from https://dict.thinktrader.net/nativeApi/xtdata.html
is caught immediately instead of silently breaking at runtime against a real QMT install.
"""

from __future__ import annotations

from typing import Any

import pytest

from qmtcli.cli import main
from qmtcli.gateway import QMTGateway


@pytest.fixture
def call_log(monkeypatch) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def fake_call_data(method: str, *args: Any, **kwargs: Any) -> Any:
        calls.append((method, args, kwargs))
        return {"method": method}

    monkeypatch.setattr(QMTGateway, "call_data", fake_call_data)
    return calls


DATA_COMMAND_CASES = [
    (
        ["calendar", "SH"],
        ("get_trading_calendar", ("SH",), {"start_time": "", "end_time": ""}),
    ),
    (
        ["calendar", "SH", "--start", "20240101", "--end", "20241231"],
        ("get_trading_calendar", ("SH",), {"start_time": "20240101", "end_time": "20241231"}),
    ),
    (
        ["trading-dates", "SH", "--count", "5"],
        ("get_trading_dates", ("SH",), {"start_time": "", "end_time": "", "count": 5}),
    ),
    (
        ["sector-list"],
        ("get_sector_list", (), {}),
    ),
    (
        ["sector-stocks", "沪深A股"],
        ("get_stock_list_in_sector", ("沪深A股",), {}),
    ),
    (
        ["full-tick", "600519.SH", "000001.SZ"],
        ("get_full_tick", (["600519.SH", "000001.SZ"],), {}),
    ),
    (
        ["bars", "600519.SH", "--start", "20240101", "--dividend-type", "front"],
        (
            "get_market_data_ex",
            ([], ["600519.SH"]),
            {
                "period": "1d",
                "start_time": "20240101",
                "end_time": "",
                "count": -1,
                "dividend_type": "front",
                "fill_data": True,
            },
        ),
    ),
    (
        ["bars", "600519.SH", "--no-fill-data"],
        (
            "get_market_data_ex",
            ([], ["600519.SH"]),
            {
                "period": "1d",
                "start_time": "",
                "end_time": "",
                "count": -1,
                "dividend_type": "none",
                "fill_data": False,
            },
        ),
    ),
    (
        ["l2-quote", "600519.SH"],
        ("get_l2_quote", ([], "600519.SH"), {"start_time": "", "end_time": "", "count": -1}),
    ),
    (
        ["l2-order", "600519.SH", "--fields", "price", "volume"],
        (
            "get_l2_order",
            (["price", "volume"], "600519.SH"),
            {"start_time": "", "end_time": "", "count": -1},
        ),
    ),
    (
        ["l2-transaction", "600519.SH"],
        ("get_l2_transaction", ([], "600519.SH"), {"start_time": "", "end_time": "", "count": -1}),
    ),
    (
        ["instrument-detail", "600519.SH", "--complete"],
        ("get_instrument_detail", ("600519.SH", True), {}),
    ),
    (
        ["instrument-detail", "600519.SH"],
        ("get_instrument_detail", ("600519.SH", False), {}),
    ),
    (
        ["instrument-type", "600519.SH"],
        ("get_instrument_type", ("600519.SH",), {}),
    ),
    (
        ["divid-factors", "600519.SH"],
        ("get_divid_factors", ("600519.SH",), {"start_time": "", "end_time": ""}),
    ),
    (
        ["holidays"],
        ("get_holidays", (), {}),
    ),
    (
        ["period-list"],
        ("get_period_list", (), {}),
    ),
    (
        ["ipo-info"],
        ("get_ipo_info", (), {"start_time": "", "end_time": ""}),
    ),
    (
        ["cb-info", "123001.SZ"],
        ("get_cb_info", ("123001.SZ",), {}),
    ),
    (
        ["etf-info"],
        ("get_etf_info", (), {}),
    ),
    (
        ["index-weight", "000300.SH"],
        ("get_index_weight", ("000300.SH",), {}),
    ),
    (
        ["financials", "600519.SH", "--tables", "Balance"],
        (
            "get_financial_data",
            (["600519.SH"],),
            {"table_list": ["Balance"], "start_time": "", "end_time": "", "report_type": "report_time"},
        ),
    ),
    (
        ["download", "history", "600519.SH", "--period", "1d", "--incrementally"],
        (
            "download_history_data2",
            (["600519.SH"], "1d"),
            {"start_time": "", "end_time": "", "incrementally": True},
        ),
    ),
    (
        ["download", "history", "600519.SH"],
        (
            "download_history_data2",
            (["600519.SH"], "1d"),
            {"start_time": "", "end_time": "", "incrementally": None},
        ),
    ),
    (
        ["download", "financials", "600519.SH", "--tables", "Balance"],
        ("download_financial_data", (["600519.SH"],), {"table_list": ["Balance"]}),
    ),
    (
        ["download", "sectors"],
        ("download_sector_data", (), {}),
    ),
    (
        ["download", "index-weight"],
        ("download_index_weight", (), {}),
    ),
    (
        ["download", "cb"],
        ("download_cb_data", (), {}),
    ),
    (
        ["download", "etf"],
        ("download_etf_info", (), {}),
    ),
    (
        ["download", "holidays"],
        ("download_holiday_data", (), {}),
    ),
    (
        ["download", "history-contracts"],
        ("download_history_contracts", (), {}),
    ),
    (
        ["data-call", "get_stock_list_in_sector", "--args", '["沪深A股"]'],
        ("get_stock_list_in_sector", ("沪深A股",), {}),
    ),
]


@pytest.mark.parametrize("argv,expected_call", DATA_COMMAND_CASES)
def test_data_command_dispatches_expected_call_data(call_log, capsys, argv, expected_call):
    assert main(argv) == 0
    assert call_log == [expected_call]


def test_calendar_without_market_exits_with_argparse_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["calendar"])
    assert exc.value.code == 2


def test_trading_dates_without_market_exits_with_argparse_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["trading-dates"])
    assert exc.value.code == 2


def test_download_history_without_symbols_errors():
    with pytest.raises(SystemExit, match="requires one or more symbols"):
        main(["download", "history"])


def test_download_financials_without_symbols_errors():
    with pytest.raises(SystemExit, match="requires one or more symbols"):
        main(["download", "financials"])


def test_download_unknown_target_rejected_by_argparse():
    with pytest.raises(SystemExit) as exc:
        main(["download", "not-a-real-target"])
    assert exc.value.code == 2
