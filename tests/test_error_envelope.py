"""CLI clean error envelope (item 2).

Any exception raised while handling a data/account command is reported as
{"ok": false, "error": "<message>"} on stdout with exit code 1, instead of a raw Python traceback.
argparse's own SystemExit (bad args, --help, missing --account) is unaffected and still propagates
as a real SystemExit. Success output keeps its original, unwrapped ("raw") shape.
"""

from __future__ import annotations

import io
import json
import sys
import types

import pytest

from qmtcli.cli import main
from qmtcli.gateway import QMTGateway


def test_data_command_exception_becomes_clean_error_envelope(monkeypatch, capsys):
    def boom(method, *args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(QMTGateway, "call_data", boom)

    assert main(["calendar", "SH"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "boom"}


def test_account_command_exception_becomes_clean_error_envelope(monkeypatch, capsys):
    def boom(self, subscribe=True):
        raise RuntimeError("connect boom")

    monkeypatch.setattr(QMTGateway, "connect", boom)

    assert main(["--account", "123456", "asset"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "connect boom"}


def test_data_call_unknown_method_becomes_clean_error_envelope(monkeypatch, capsys):
    # data-call's method name is a free-text argument argparse cannot validate, so a private
    # method name reaches QMTGateway.call_data's own ValueError for real (fake xtdata module,
    # matching test_boundaries.py::test_data_call_blocks_private_methods, so no broker QMT needed).
    monkeypatch.setitem(sys.modules, "xtquant.xtdata", types.ModuleType("xtquant.xtdata"))

    assert main(["data-call", "_private_or_missing_method"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "unknown xtdata method" in payload["error"]


def test_argparse_missing_required_arg_still_raises_system_exit():
    with pytest.raises(SystemExit) as exc:
        main(["calendar"])

    assert exc.value.code == 2


def test_argparse_help_still_raises_system_exit_zero():
    with pytest.raises(SystemExit) as exc:
        main(["--help"])

    assert exc.value.code == 0


def test_success_output_stays_raw_and_unwrapped(monkeypatch, capsys):
    monkeypatch.setattr(QMTGateway, "call_data", lambda method, *a, **kw: ["2024-01-01"])

    assert main(["calendar", "SH"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload == ["2024-01-01"]


def test_rpc_path_error_envelope_is_unaffected_by_the_new_cli_wrapper(monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"command":"missing"}'))

    assert main(["rpc"]) == 0  # rpc always exits 0; failure is reported inside the JSON body

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "unknown command" in payload["error"]
