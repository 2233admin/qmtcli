"""CLI-only `watch` command: subscribes then blocks on xtdata.run(), streaming JSONL quote events.

Unlike subscribe/subscribe_whole (server mode only, see test_subscribe.py), `watch` drives
subscribe_quote/subscribe_whole_quote directly via call_data from the CLI, then blocks in
call_data("run") until interrupted. It is deliberately excluded from DATA_COMMAND_NAMES and is
never reachable over rpc/server; server mode already has subscribe/subscribe_whole/unsubscribe for
the same purpose.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from qmtcli.cli import DATA_COMMAND_NAMES, main
from qmtcli.gateway import QMTGateway


@pytest.fixture
def call_log(monkeypatch) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def fake_call_data(method: str, *args: Any, **kwargs: Any) -> Any:
        calls.append((method, args, kwargs))
        if method == "run":
            return None
        return 1

    monkeypatch.setattr(QMTGateway, "call_data", fake_call_data)
    return calls


def test_watch_is_not_routed_through_the_generic_data_command_dispatcher():
    assert "watch" not in DATA_COMMAND_NAMES


def test_watch_subscribes_each_symbol_then_runs(call_log):
    assert main(["watch", "600519.SH", "000001.SZ"]) == 0

    methods = [call[0] for call in call_log]
    assert methods == ["subscribe_quote", "subscribe_quote", "run"]

    first_call, second_call = call_log[0], call_log[1]
    assert first_call[1] == ("600519.SH",)
    assert first_call[2]["period"] == "1m"
    assert first_call[2]["count"] == 0
    assert callable(first_call[2]["callback"])
    assert second_call[1] == ("000001.SZ",)
    assert second_call[2]["period"] == "1m"


def test_watch_defaults_period_to_1m(call_log):
    assert main(["watch", "600519.SH"]) == 0

    assert call_log[0][2]["period"] == "1m"


def test_watch_honors_explicit_period_flag(call_log):
    assert main(["watch", "600519.SH", "--period", "5m"]) == 0

    assert call_log[0][2]["period"] == "5m"


def test_watch_whole_flag_uses_single_subscribe_whole_quote_call(call_log):
    assert main(["watch", "600519.SH", "000001.SZ", "--whole"]) == 0

    methods = [call[0] for call in call_log]
    assert methods == ["subscribe_whole_quote", "run"]
    assert call_log[0][1] == (["600519.SH", "000001.SZ"],)
    assert callable(call_log[0][2]["callback"])


def test_watch_quote_callback_emits_event_json(call_log, capsys):
    assert main(["watch", "600519.SH"]) == 0
    # main() bypasses _print_json for watch, so nothing has been printed yet at this point.
    assert capsys.readouterr().out == ""

    callback = call_log[0][2]["callback"]
    callback({"600519.SH": {"lastPrice": 10}})

    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    event = json.loads(out[0])
    assert event == {
        "event": "quote",
        "symbol": "600519.SH",
        "data": {"600519.SH": {"lastPrice": 10}},
    }


def test_watch_each_symbol_callback_reports_its_own_symbol(call_log, capsys):
    assert main(["watch", "600519.SH", "000001.SZ"]) == 0

    call_log[0][2]["callback"]({"600519.SH": {"lastPrice": 10}})
    call_log[1][2]["callback"]({"000001.SZ": {"lastPrice": 20}})

    out = capsys.readouterr().out.strip().splitlines()
    events = [json.loads(line) for line in out]
    assert events == [
        {"event": "quote", "symbol": "600519.SH", "data": {"600519.SH": {"lastPrice": 10}}},
        {"event": "quote", "symbol": "000001.SZ", "data": {"000001.SZ": {"lastPrice": 20}}},
    ]


def test_watch_whole_callback_emits_whole_quote_event_json(call_log, capsys):
    assert main(["watch", "600519.SH", "000001.SZ", "--whole"]) == 0

    callback = call_log[0][2]["callback"]
    callback({"600519.SH": {"lastPrice": 10}})

    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    event = json.loads(out[0])
    assert event == {"event": "whole_quote", "data": {"600519.SH": {"lastPrice": 10}}}


def test_watch_keyboard_interrupt_from_run_exits_cleanly(monkeypatch):
    def fake_call_data(method: str, *args: Any, **kwargs: Any) -> Any:
        if method == "run":
            raise KeyboardInterrupt
        return 1

    monkeypatch.setattr(QMTGateway, "call_data", fake_call_data)

    assert main(["watch", "600519.SH"]) == 0


def test_watch_keyboard_interrupt_whole_mode_also_exits_cleanly(monkeypatch):
    def fake_call_data(method: str, *args: Any, **kwargs: Any) -> Any:
        if method == "run":
            raise KeyboardInterrupt
        return 1

    monkeypatch.setattr(QMTGateway, "call_data", fake_call_data)

    assert main(["watch", "600519.SH", "000001.SZ", "--whole"]) == 0


def test_watch_requires_at_least_one_symbol():
    with pytest.raises(SystemExit) as exc:
        main(["watch"])
    assert exc.value.code == 2


def test_watch_capabilities_entry_is_cli_only():
    from qmtcli.cli import AGENT_CAPABILITIES

    entry = next(c for c in AGENT_CAPABILITIES["commands"] if c["name"] == "watch")
    assert entry["transports"] == ["cli"]
    assert entry["danger"] == "safe"
