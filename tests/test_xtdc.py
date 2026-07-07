"""Standalone xtdatacenter (xtdc) data mode (item 5, experimental).

--xtdc-token (env fallback QMTCLI_XTDC_TOKEN) + --xtdc-port make qmtcli call
xtquant.xtdatacenter.set_token()/.init() once, before any command runs, via
QMTGateway.init_xtdc(). Idempotent: a second init_xtdc call (e.g. a later request in `server` mode)
is a no-op. With no token, xtdatacenter must never be touched at all.
"""

from __future__ import annotations

import importlib
import json
import sys
import types

import pytest

from qmtcli.cli import main
from qmtcli.gateway import QMTGateway


@pytest.fixture(autouse=True)
def _reset_xtdc_state(monkeypatch):
    """QMTGateway._xtdc_initialized is a class attribute; reset it so tests do not leak state."""
    monkeypatch.setattr(QMTGateway, "_xtdc_initialized", False)


def test_init_xtdc_calls_set_token_and_init(monkeypatch):
    calls = []
    fake_xtdc = types.ModuleType("xtquant.xtdatacenter")
    fake_xtdc.set_token = lambda token: calls.append(("set_token", token))
    fake_xtdc.init = lambda: calls.append(("init",))
    monkeypatch.setitem(sys.modules, "xtquant.xtdatacenter", fake_xtdc)

    QMTGateway.init_xtdc("MY_TOKEN")

    assert calls == [("set_token", "MY_TOKEN"), ("init",)]


def test_init_xtdc_is_idempotent(monkeypatch):
    calls = []
    fake_xtdc = types.ModuleType("xtquant.xtdatacenter")
    fake_xtdc.set_token = lambda token: calls.append(("set_token", token))
    fake_xtdc.init = lambda: calls.append(("init",))
    monkeypatch.setitem(sys.modules, "xtquant.xtdatacenter", fake_xtdc)

    QMTGateway.init_xtdc("MY_TOKEN")
    QMTGateway.init_xtdc("MY_TOKEN")
    QMTGateway.init_xtdc("A_DIFFERENT_TOKEN")

    assert calls == [("set_token", "MY_TOKEN"), ("init",)]


def test_no_token_never_calls_init_xtdc(monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMTGateway,
        "init_xtdc",
        classmethod(lambda cls, token, port=58620: calls.append((token, port))),
    )

    assert main(["status"]) == 0

    assert calls == []


def test_xtdc_token_flag_calls_init_xtdc_before_dispatch(monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMTGateway,
        "init_xtdc",
        classmethod(lambda cls, token, port=58620: calls.append((token, port))),
    )

    assert main(["--xtdc-token", "FLAG_TOKEN", "--xtdc-port", "12345", "status"]) == 0

    assert calls == [("FLAG_TOKEN", 12345)]


def test_xtdc_token_env_var_fallback(monkeypatch):
    monkeypatch.setenv("QMTCLI_XTDC_TOKEN", "ENV_TOKEN")
    calls = []
    monkeypatch.setattr(
        QMTGateway,
        "init_xtdc",
        classmethod(lambda cls, token, port=58620: calls.append((token, port))),
    )

    assert main(["status"]) == 0

    assert calls == [("ENV_TOKEN", 58620)]


def test_xtdc_flag_overrides_env_var(monkeypatch):
    monkeypatch.setenv("QMTCLI_XTDC_TOKEN", "ENV_TOKEN")
    calls = []
    monkeypatch.setattr(
        QMTGateway,
        "init_xtdc",
        classmethod(lambda cls, token, port=58620: calls.append((token, port))),
    )

    assert main(["--xtdc-token", "FLAG_TOKEN", "status"]) == 0

    assert calls == [("FLAG_TOKEN", 58620)]


def test_xtdc_default_port_is_58620(monkeypatch):
    calls = []
    monkeypatch.setattr(
        QMTGateway,
        "init_xtdc",
        classmethod(lambda cls, token, port=58620: calls.append(port)),
    )

    assert main(["--xtdc-token", "T", "status"]) == 0

    assert calls == [58620]


def test_xtdc_init_import_failure_becomes_clean_error_envelope(monkeypatch, capsys):
    real_import_module = importlib.import_module

    def broken_import(name, *args, **kwargs):
        if name == "xtquant.xtdatacenter":
            raise ImportError("no xtdatacenter here")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", broken_import)

    assert main(["--xtdc-token", "BROKEN", "status"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "no xtdatacenter here" in payload["error"]


def test_doctor_reports_xtdc_available_key_present(capsys):
    assert main(["doctor"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert "xtdc_available" in payload
    assert isinstance(payload["xtdc_available"], bool)
