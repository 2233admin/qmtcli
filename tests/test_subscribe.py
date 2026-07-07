"""Server-mode subscription streaming: subscribe / subscribe_whole / unsubscribe.

These three commands wrap xtdata's callback-based subscribe_quote / subscribe_whole_quote /
unsubscribe_quote. The callback fires on a background thread while the `server` JSONL loop blocks
on stdin, so they only make sense in server mode and are rejected everywhere else (one-shot `rpc`,
CLI).
"""

from __future__ import annotations

import io
import json
import sys
from typing import Any

import pytest

from qmtcli.cli import _handle_rpc_request, main
from qmtcli.gateway import QMTGateway


@pytest.fixture
def captured_callback(monkeypatch) -> dict[str, Any]:
    """Fake call_data that returns seq=42 for subscribe_* and records every call."""
    state: dict[str, Any] = {"callback": None, "calls": []}

    def fake_call_data(method: str, *args: Any, **kwargs: Any) -> Any:
        state["calls"].append((method, args, kwargs))
        if method in {"subscribe_quote", "subscribe_whole_quote"}:
            state["callback"] = kwargs.get("callback")
            return 42
        if method == "unsubscribe_quote":
            return 0
        raise AssertionError(f"unexpected call_data method: {method}")

    monkeypatch.setattr(QMTGateway, "call_data", fake_call_data)
    return state


def test_subscribe_returns_seq_and_streams_quote_event(captured_callback, capsys):
    response = _handle_rpc_request({"command": "subscribe", "symbol": "600519.SH"}, allow_subscribe=True)

    assert response == {"ok": True, "data": {"seq": 42}}

    callback = captured_callback["callback"]
    assert callable(callback)
    callback({"600519.SH": {"lastPrice": 10}})

    out = capsys.readouterr().out.strip()
    lines = out.splitlines()
    assert len(lines) == 1
    event = json.loads(lines[0])
    assert event == {
        "event": "quote",
        "seq": 42,
        "symbol": "600519.SH",
        "data": {"600519.SH": {"lastPrice": 10}},
    }


def test_subscribe_passes_period_and_count_defaults_and_symbol_positionally(captured_callback):
    _handle_rpc_request({"command": "subscribe", "symbol": "600519.SH"}, allow_subscribe=True)

    method, args, kwargs = captured_callback["calls"][0]
    assert method == "subscribe_quote"
    assert args == ("600519.SH",)
    assert kwargs["period"] == "1d"
    assert kwargs["count"] == 0
    assert callable(kwargs["callback"])


def test_subscribe_honors_explicit_period_and_count(captured_callback):
    _handle_rpc_request(
        {"command": "subscribe", "symbol": "600519.SH", "period": "1m", "count": 5},
        allow_subscribe=True,
    )

    _method, _args, kwargs = captured_callback["calls"][0]
    assert kwargs["period"] == "1m"
    assert kwargs["count"] == 5


def test_subscribe_whole_streams_whole_quote_event(captured_callback, capsys):
    response = _handle_rpc_request(
        {"command": "subscribe_whole", "symbols": ["600519.SH", "000001.SZ"]},
        allow_subscribe=True,
    )

    assert response == {"ok": True, "data": {"seq": 42}}

    callback = captured_callback["callback"]
    callback({"600519.SH": {"lastPrice": 10}})

    out = capsys.readouterr().out.strip()
    event = json.loads(out.splitlines()[0])
    assert event == {
        "event": "whole_quote",
        "seq": 42,
        "symbols": ["600519.SH", "000001.SZ"],
        "data": {"600519.SH": {"lastPrice": 10}},
    }


def test_unsubscribe_maps_to_unsubscribe_quote(captured_callback):
    response = _handle_rpc_request({"command": "unsubscribe", "seq": 42}, allow_subscribe=True)

    assert response == {"ok": True, "data": {"unsubscribed": 42}}
    assert captured_callback["calls"] == [("unsubscribe_quote", (42,), {})]


def test_one_shot_rpc_path_rejects_subscribe(captured_callback):
    response = _handle_rpc_request({"command": "subscribe", "symbol": "600519.SH"})

    assert response["ok"] is False
    assert "server mode" in response["error"]
    assert captured_callback["calls"] == []


def test_one_shot_rpc_path_rejects_subscribe_whole(captured_callback):
    response = _handle_rpc_request({"command": "subscribe_whole", "symbols": ["600519.SH"]})

    assert response["ok"] is False
    assert "server mode" in response["error"]
    assert captured_callback["calls"] == []


def test_one_shot_rpc_path_rejects_unsubscribe(captured_callback):
    response = _handle_rpc_request({"command": "unsubscribe", "seq": 42})

    assert response["ok"] is False
    assert "server mode" in response["error"]
    assert captured_callback["calls"] == []


def test_subscribe_requires_symbol(captured_callback):
    response = _handle_rpc_request({"command": "subscribe"}, allow_subscribe=True)

    assert response["ok"] is False
    assert "requires symbol" in response["error"]


def test_subscribe_whole_requires_symbols(captured_callback):
    response = _handle_rpc_request({"command": "subscribe_whole"}, allow_subscribe=True)

    assert response["ok"] is False
    assert "requires symbols" in response["error"]


def test_unsubscribe_requires_seq(captured_callback):
    response = _handle_rpc_request({"command": "unsubscribe"}, allow_subscribe=True)

    assert response["ok"] is False
    assert "requires seq" in response["error"]


def test_server_loop_allows_subscribe_and_emits_compact_json(monkeypatch, capsys, captured_callback):
    monkeypatch.setattr(
        sys, "stdin", io.StringIO('{"id":1,"command":"subscribe","symbol":"600519.SH"}\n')
    )

    assert main(["server"]) == 0

    out = capsys.readouterr().out.strip()
    lines = out.splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"ok": True, "data": {"seq": 42}, "id": 1}


def test_server_loop_can_unsubscribe(monkeypatch, capsys, captured_callback):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"command":"unsubscribe","seq":42}\n'))

    assert main(["server"]) == 0

    out = capsys.readouterr().out.strip()
    assert json.loads(out.splitlines()[0]) == {"ok": True, "data": {"unsubscribed": 42}}
