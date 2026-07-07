from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from qmtcli.cli import _handle_rpc_request
from qmtcli.gateway import QMTConnection, QMTGateway


def test_data_call_blocks_private_methods(monkeypatch):
    monkeypatch.setitem(sys.modules, "xtquant.xtdata", types.ModuleType("xtquant.xtdata"))

    with pytest.raises(ValueError, match="unknown xtdata method"):
        QMTGateway.call_data("_private")


def test_trade_call_blocks_private_methods():
    gateway = QMTGateway(QMTConnection("C:/qmt/userdata_mini", "123456"))
    gateway.trader = object()
    gateway.account = object()

    with pytest.raises(ValueError, match="unknown XtQuantTrader method"):
        gateway.call_trader("_private")


def test_rpc_unknown_command_returns_error_without_id():
    response = _handle_rpc_request({"command": "missing"})

    assert response["ok"] is False
    assert "unknown command" in response["error"]
    assert "id" not in response


def test_rpc_error_echoes_id():
    response = _handle_rpc_request({"id": 7, "command": "missing"})

    assert response["ok"] is False
    assert response["id"] == 7


def test_examples_are_valid_json():
    for path in [
        Path("examples/status.json"),
        Path("examples/order.json"),
        Path("examples/data_call.json"),
    ]:
        assert json.loads(path.read_text(encoding="utf-8"))["command"]
