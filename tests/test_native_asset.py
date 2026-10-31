"""Native read-only asset contracts; fixtures contain fictional financial values."""
import math
import struct

import pytest

from qmtcli.native_asset import (
    WORKER_MARKER, _parse_worker_output, decode_asset, decode_frame, encode_account, encode_frame,
)


def test_connection_frame_matches_recovered_envelope():
    raw = encode_frame(7, 10001, 123, struct.pack("<qi", 123, 456), bucket_size=64)
    assert raw[:24].hex() == "070000000000000011270000000100007b00000000000000"
    assert raw[24:36].hex() == "7b00000000000000c8010000"
    assert len(raw) == 64
    assert decode_frame(raw) == (7, 10001, 0, True, 123, raw[24:])


def test_native_read_request_allowlist_excludes_trading_operations():
    assert decode_frame(encode_frame(1, 20007, 123, encode_account("A", "STOCK")))[1] == 20007
    for forbidden in (20001, 20003, 20009, 50001):
        with pytest.raises(ValueError, match="read-only"):
            encode_frame(1, forbidden, 123, b"")


@pytest.mark.parametrize("account", ["", "A" * 24, "a\x00b", "账户"])
def test_account_requires_nonempty_ascii_c_string(account):
    with pytest.raises(ValueError, match="account"):
        encode_account(account, "STOCK")


def test_stock_account_request_has_24_byte_account_buffer():
    expected = bytes.fromhex("02000000") + b"123456" + bytes(18)
    assert encode_account("123456", "STOCK") == expected
    assert len(expected) == 28
    with pytest.raises(ValueError, match="STOCK"):
        encode_account("123456", "FUTURE")


def asset_fixture(**overrides):
    values = dict(cash=1250.25, frozen_cash=50.0, market_value=5000.0, total_asset=6300.25)
    values.update(overrides)
    return struct.pack("<i24s6d", 2, b"123456", *values.values(), 999.0, 888.0)


def test_asset_decode_preserves_sdk_public_fields_without_naming_unknown_tail():
    assert decode_asset(asset_fixture(), "123456") == {
        "account_type": 2, "account_id": "123456", "cash": 1250.25,
        "frozen_cash": 50.0, "market_value": 5000.0, "total_asset": 6300.25,
    }


def test_zero_asset_is_valid_and_wrong_account_is_rejected():
    assert decode_asset(asset_fixture(cash=0.0), "123456")["cash"] == 0.0
    with pytest.raises(ValueError, match="account"):
        decode_asset(asset_fixture(), "654321")


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_nonfinite_assets_are_rejected(value):
    with pytest.raises(ValueError, match="finite"):
        decode_asset(asset_fixture(cash=value), "123456")


def test_truncated_response_and_unknown_status_are_rejected():
    with pytest.raises(ValueError, match="76"):
        decode_asset(asset_fixture()[:60], "123456")
    with pytest.raises(ValueError, match="header"):
        decode_frame(bytes(23))
    raw = bytearray(encode_frame(1, 20005, 123, encode_account("123456", "STOCK")))
    raw[12] = 99
    with pytest.raises(ValueError, match="action"):
        decode_frame(raw)


def test_worker_diagnostics_do_not_pollute_json_result():
    assert _parse_worker_output('noise\n' + WORKER_MARKER + '{"ok":true,"data":{}}\n0\n') == {
        "ok": True, "data": {},
    }
    with pytest.raises(RuntimeError, match="invalid JSON"):
        _parse_worker_output('{"ok":true}\n')
    with pytest.raises(RuntimeError, match="invalid JSON"):
        _parse_worker_output((WORKER_MARKER + '{"ok":true}\n') * 2)


def test_native_asset_cli_never_connects_sdk(monkeypatch, capsys):
    import json
    from qmtcli.cli import main
    from qmtcli.gateway import QMTGateway
    import qmtcli.native_asset as native

    def forbidden(*args, **kwargs):
        pytest.fail("native asset must not initialize SDK")

    monkeypatch.setattr(QMTGateway, "connect", forbidden)
    monkeypatch.setattr(QMTGateway, "init_xtdc", forbidden)
    monkeypatch.setenv("QMTCLI_XTDC_TOKEN", "ignored-for-native-assets")
    calls = []

    def query(path, account, account_type, timeout):
        calls.append((path, account, account_type, timeout))
        return {"account_id": account, "cash": 1250.25}

    monkeypatch.setattr(native, "query_native_asset", query)
    assert main(["--path", "C:/qmt/userdata_mini", "--account", "123456",
                 "asset", "--backend", "native", "--timeout", "2"]) == 0
    assert json.loads(capsys.readouterr().out)["cash"] == 1250.25
    assert calls == [("C:/qmt/userdata_mini", "123456", "STOCK", 2.0)]


def test_rpc_native_asset_preserves_id_and_error_contract(monkeypatch):
    from qmtcli.cli import _handle_rpc_request
    from qmtcli.gateway import QMTGateway
    import qmtcli.native_asset as native

    monkeypatch.setattr(QMTGateway, "connect", lambda *a, **kw: pytest.fail("SDK connected"))
    monkeypatch.setattr(native, "query_native_asset", lambda *a: {"cash": 0.0})
    request = {"id": "n1", "command": "asset", "backend": "native", "account": "123456",
               "path": "C:/qmt/userdata_mini"}
    assert _handle_rpc_request(request) == {"id": "n1", "ok": True, "data": {"cash": 0.0}}

    def timed_out(*args):
        raise TimeoutError("native asset timeout")

    monkeypatch.setattr(native, "query_native_asset", timed_out)
    assert _handle_rpc_request(request) == {
        "id": "n1", "ok": False, "error": "native asset timeout",
    }


@pytest.mark.parametrize("payload", [
    {"command": "asset", "backend": "unknown"},
    {"command": "positions", "backend": "native"},
])
def test_invalid_backend_does_not_silently_select_sdk(payload, monkeypatch):
    from qmtcli.cli import _handle_rpc_request
    from qmtcli.gateway import QMTGateway

    monkeypatch.setattr(QMTGateway, "connect", lambda *a, **kw: pytest.fail("SDK connected"))
    assert _handle_rpc_request(payload)["ok"] is False


def test_native_backend_is_discoverable_in_capabilities_and_mcp():
    from qmtcli.cli import AGENT_CAPABILITIES, AGENT_SCHEMA
    asset = next(c for c in AGENT_CAPABILITIES["commands"] if c["name"] == "asset")
    assert "native" in asset["inputs"]["backend"]
    assert "backend" in AGENT_SCHEMA["request"]
    pytest.importorskip("mcp")
    from qmtcli.mcp_server import build_tool_specs
    tool = next(t for t in build_tool_specs() if t["name"] == "qmt_asset")
    assert "backend" in tool["inputSchema"]["properties"]


@pytest.fixture
def native_install(tmp_path, monkeypatch):
    import qmtcli.native_asset as native
    data = tmp_path / "userdata_mini"
    data.mkdir()
    (data / "up_queue_xtquant").touch()
    monkeypatch.setattr(native, "_validate_runtime", lambda folder: None)
    return tmp_path, data


def test_worker_timeout_cleans_only_its_owned_reply(native_install, monkeypatch):
    import json
    import subprocess
    import qmtcli.native_asset as native
    root, data = native_install
    unrelated = data / "down_queue_someone_else"
    unrelated.write_bytes(b"keep")

    def timeout(*args, **kwargs):
        request_data = json.loads(kwargs["input"])
        assert (data / f"down_queue_{request_data['session']}").exists()
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(native.subprocess, "run", timeout)
    with pytest.raises(TimeoutError, match="deadline"):
        native.query_native_asset(str(root), "123456", timeout=0.2)
    assert list(data.glob("down_queue_*")) == [unrelated]
    assert unrelated.read_bytes() == b"keep"


def test_native_session_collision_does_not_overwrite_or_delete(native_install, monkeypatch):
    import qmtcli.native_asset as native
    root, data = native_install
    existing = data / "down_queue_7"
    existing.write_bytes(b"another client")
    monkeypatch.setattr(native.secrets, "randbelow", lambda bound: 6)
    with pytest.raises(FileExistsError):
        native.query_native_asset(str(root), "123456")
    assert existing.read_bytes() == b"another client"


def test_direct_worker_cannot_truncate_an_existing_client_queue(native_install):
    import qmtcli.native_asset as native
    root, data = native_install
    existing = data / "down_queue_7"
    existing.write_bytes(b"another client")
    with pytest.raises(RuntimeError, match="not owned"):
        native._worker({"path": str(root), "account": "123456", "session": 7,
                        "timeout": 1, "owner": "unrelated"})
    assert existing.read_bytes() == b"another client"


def test_native_worker_fault_is_an_error_without_sdk_fallback(native_install, monkeypatch):
    from types import SimpleNamespace
    import qmtcli.native_asset as native
    root, data = native_install
    monkeypatch.setattr(native.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=139))
    with pytest.raises(RuntimeError, match="exit 139"):
        native.query_native_asset(str(root), "123456")
    assert not list(data.glob("down_queue_*"))


@pytest.mark.parametrize("timeout", [0, 61, True, "5", math.nan])
def test_invalid_timeout_is_rejected_before_connecting(timeout):
    from qmtcli.native_asset import query_native_asset
    with pytest.raises(ValueError, match="timeout"):
        query_native_asset("C:/not-used", "123456", timeout=timeout)


def test_unrecognized_binary_build_is_rejected(tmp_path, monkeypatch):
    import qmtcli.native_asset as native
    monkeypatch.setattr(native.sys, "platform", "win32")
    (tmp_path / "ringbuffer.dll").write_bytes(b"unverified build")
    with pytest.raises(RuntimeError, match="fingerprint"):
        native._validate_runtime(tmp_path)


@pytest.mark.parametrize("transport", ["rpc", "server"])
def test_native_stdio_request_ignores_inherited_data_token(transport, monkeypatch, capsys):
    import io
    import json
    import sys
    from qmtcli.cli import main
    from qmtcli.gateway import QMTGateway
    import qmtcli.native_asset as native

    monkeypatch.setenv("QMTCLI_XTDC_TOKEN", "not-needed-for-assets")
    monkeypatch.setattr(QMTGateway, "init_xtdc", lambda *a: pytest.fail("SDK initialized"))
    monkeypatch.setattr(native, "query_native_asset", lambda *a: {"cash": 0.0})
    from qmtcli.account_session import AccountSession
    monkeypatch.setattr(AccountSession, "native_query", lambda *a: {"cash": 0.0})
    payload = {"command": "asset", "backend": "native", "account": "123456",
               "path": "C:/qmt/userdata_mini"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload) + "\n"))
    assert main([transport]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "data": {"cash": 0.0}}


def test_jsonl_defers_sdk_token_until_non_native_request(monkeypatch, capsys):
    import io
    import json
    import sys
    from qmtcli.cli import main
    from qmtcli.gateway import QMTGateway
    import qmtcli.native_asset as native

    initialized = []
    monkeypatch.setenv("QMTCLI_XTDC_TOKEN", "fake-token")
    monkeypatch.setattr(QMTGateway, "init_xtdc", lambda *args: initialized.append(args))
    monkeypatch.setattr(QMTGateway, "is_available", lambda path: False)

    def query(*args):
        assert not initialized
        return {"cash": 0.0}

    monkeypatch.setattr(native, "query_native_asset", query)
    from qmtcli.account_session import AccountSession
    monkeypatch.setattr(AccountSession, "native_query", query)
    native_request = {"command": "asset", "backend": "native", "account": "123456",
                      "path": "C:/qmt/userdata_mini"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(
        json.dumps(native_request) + '\n{"command":"status"}\n'))
    assert main(["server"]) == 0
    responses = [json.loads(s) for s in capsys.readouterr().out.splitlines()]
    assert len(responses) == 2 and all(r["ok"] for r in responses)
    assert initialized == [("fake-token", 58620)]


def test_native_mcp_session_does_not_initialize_sdk_token(monkeypatch):
    pytest.importorskip("mcp")
    import anyio
    import json
    from mcp.shared.memory import create_connected_server_and_client_session
    from qmtcli.gateway import QMTGateway
    from qmtcli.mcp_server import build_server
    import qmtcli.native_asset as native

    monkeypatch.setattr(QMTGateway, "init_xtdc", lambda *a: pytest.fail("SDK initialized"))
    monkeypatch.setattr(native, "query_native_asset", lambda *a: {"cash": 0.0})

    async def scenario():
        async with create_connected_server_and_client_session(build_server(("fake-token", 58620))) as client:
            result = await client.call_tool("qmt_asset", {
                "backend": "native", "account": "123456", "path": "C:/qmt/userdata_mini",
            })
            assert json.loads(result.content[0].text) == {"ok": True, "data": {"cash": 0.0}}

    anyio.run(scenario)
