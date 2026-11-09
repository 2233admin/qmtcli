"""Pinned native trade response contracts, including explicit empty completion."""
import struct

import pytest

from qmtcli.native_trades import TradeReplies, decode_trade


def asset(account="A"):
    return struct.pack("<i24s6d", 2, account.encode(), 10, 0, 20, 30, 0, 0)


def trade(identifier="T1"):
    raw = bytearray(552)
    struct.pack_into("<i24s", raw, 0, 2, b"A")
    for offset, value in [(28, "600000.SH"), (44, identifier), (104, "SYS1"),
                          (128, "strategy"), (152, "remark"), (312, identifier),
                          (392, "600000.SH"), (184, "备注")]:
        encoded = value.encode()
        raw[offset:offset + len(encoded)] = encoded
    struct.pack_into("<qdidii", raw, 68, 93500, 10.5, 100, 1050.0, 7, 23)
    return bytes(raw)


def validated():
    replies = TradeReplies("A", 123)
    assert replies.feed((2, 30001, 1, True, 123, asset())) is None
    return replies


def test_native_trade_public_fields():
    assert decode_trade(trade(), "A") == {
        "account_type": 2, "account_id": "A", "stock_code": "600000.SH",
        "traded_id": "T1", "traded_time": 93500, "traded_price": 10.5,
        "traded_volume": 100, "traded_amount": 1050.0, "order_id": 7,
        "order_type": 23, "order_sysid": "SYS1", "strategy_name": "strategy",
        "order_remark": "备注",
    }


def test_only_explicit_empty_response_after_account_validation_is_empty():
    assert validated().feed((3, 20000, 1, True, 123, struct.pack("<q", -1))) == []
    with pytest.raises(ValueError, match="validated"):
        TradeReplies("A", 123).feed((3, 20000, 1, True, 123, struct.pack("<q", -1)))
    with pytest.raises(ValueError):
        validated().feed((3, 20000, 1, True, 123, struct.pack("<q", -2)))


def test_nonempty_rows_reassembled_without_losing_last_flag():
    replies = validated()
    result = None
    for number, identifier in enumerate(["T1", "T2"]):
        raw = trade(identifier)
        for offset in range(0, len(raw), 450):
            chunk = raw[offset:offset + 450]
            fragment = struct.pack("<IIQQQ6x", 1, 30003, len(raw), len(chunk), offset) + chunk
            last = number == 1 and offset + len(chunk) == len(raw)
            result = replies.feed((3, 10009, 1, last, 123, fragment))
    assert [r["traded_id"] for r in result] == ["T1", "T2"]


def test_partial_or_mismatched_reply_never_becomes_empty():
    replies = validated()
    assert replies.feed((3, 30003, 1, False, 123, trade())) is None
    with pytest.raises(ValueError):
        replies.feed((3, 20000, 1, True, 123, struct.pack("<q", -1)))
    with pytest.raises(ValueError, match="session"):
        validated().feed((3, 30003, 1, True, 999, trade()))
    with pytest.raises(ValueError, match="account"):
        TradeReplies("OTHER", 123).feed((2, 30001, 1, True, 123, asset()))
    with pytest.raises(ValueError, match="duplicate"):
        validated().feed((2, 30001, 1, True, 123, asset()))


@pytest.mark.parametrize("field,value", [(0, 0), (4, 999), (8, 553), (16, 0), (24, 100)])
def test_malformed_fragments_rejected(field, value):
    raw = bytearray(struct.pack("<IIQQQ6x", 1, 30003, 552, 450, 0) + bytes(450))
    struct.pack_into("<I" if field in [0, 4] else "<Q", raw, field, value)
    with pytest.raises(ValueError, match="fragment"):
        validated().feed((3, 10009, 1, False, 123, bytes(raw)))


def test_bad_numeric_and_truncated_rows_rejected():
    with pytest.raises(ValueError):
        decode_trade(trade()[:551], "A")
    raw = bytearray(trade())
    struct.pack_into("<d", raw, 76, float("nan"))
    with pytest.raises(ValueError, match="finite"):
        decode_trade(raw, "A")


@pytest.mark.parametrize("include_rows", [True, False])
def test_worker_sends_one_trade_request_and_never_guesses_empty(monkeypatch, tmp_path, include_rows):
    import ctypes
    from qmtcli import native_asset as native
    from qmtcli import native_trades

    (tmp_path / "down_queue_123").write_bytes(b"qmtcli-native-owner:owner")
    monkeypatch.setattr(native, "_paths", lambda path: (tmp_path, tmp_path))
    monkeypatch.setattr(native, "_validate_runtime", lambda path: None)
    monkeypatch.setattr(native_trades, "validate_trade_runtime", lambda path: None)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: object(), raising=False)
    monkeypatch.setattr(native.os, "add_dll_directory", lambda path: type("Directory", (), {"close": lambda self: None})(), raising=False)
    frames = [
        (1, 10002, 1, True, 123, struct.pack("<q", 123)),
        (2, 30001, 1, True, 123, asset()),
    ]
    raw = trade()
    for offset in [0, 450]:
        chunk = raw[offset:offset + 450]
        if include_rows:
            frames.append((3, 10009, 1, offset == 450, 123,
                           struct.pack("<IIQQQ6x", 1, 30003, 552, len(chunk), offset) + chunk))
    sent = []

    class Ring:
        def __init__(self, *args, **kwargs):
            pass

        def send(self, raw, deadline):
            sent.append(native.decode_frame(raw)[1])

        def receive(self, deadline):
            yield from frames

    monkeypatch.setattr(native, "_Ring", Ring)
    request = {"path": str(tmp_path), "account": "A", "session": 123,
               "owner": "owner", "timeout": 1, "operation": "asset_trades"}
    if not include_rows:
        with pytest.raises(TimeoutError, match="account response timed out"):
            native._worker(request)
        assert sent == [10001, 20005, 20007]
        return
    result = native._worker(request)
    assert sent == [10001, 20005, 20007]
    assert result["asset"]["account_id"] == "A"
    assert result["trades"][0]["traded_id"] == "T1"


def test_native_trades_cli_and_rpc_never_connect_sdk(monkeypatch, capsys):
    import json
    from qmtcli import cli
    from qmtcli import native_trades

    monkeypatch.setattr(cli.QMTGateway, "connect", lambda *a, **k: pytest.fail("SDK connected"))
    monkeypatch.setattr(cli.QMTGateway, "init_xtdc", lambda *a, **k: pytest.fail("SDK initialized"))
    monkeypatch.setattr(native_trades, "query_native_account", lambda *a: {"asset": {}, "trades": [{"traded_id": "T1"}]})
    monkeypatch.setenv("QMTCLI_XTDC_TOKEN", "ignored")
    assert cli.main(["--path", "C:/QMT", "--account", "A", "trades", "--backend", "native"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["traded_id"] == "T1"
    response = cli._handle_rpc_request({"id": 7, "command": "trades", "backend": "native", "path": "C:/QMT", "account": "A"})
    assert response["ok"] and response["id"] == 7 and response["data"][0]["traded_id"] == "T1"


def test_worker_reuses_handshake_with_fresh_wire_sequences(monkeypatch, tmp_path):
    import ctypes
    from qmtcli import native_asset as native
    from qmtcli import native_trades

    (tmp_path / "down_queue_123").write_bytes(b"qmtcli-native-owner:owner")
    monkeypatch.setattr(native, "_paths", lambda path: (tmp_path, tmp_path))
    monkeypatch.setattr(native, "_validate_runtime", lambda path: None)
    monkeypatch.setattr(native_trades, "validate_trade_runtime", lambda path: None)
    monkeypatch.setattr(ctypes, "WinDLL", lambda *a, **k: object(), raising=False)
    monkeypatch.setattr(native.os, "add_dll_directory",
                        lambda p: type("Directory", (), {"close": lambda s: None})(), raising=False)
    frames = iter([
        (1, 10002, 1, True, 123, struct.pack("<q", 123)),
        (2, 30001, 1, True, 123, asset()), (3, 30003, 1, True, 123, trade("T1")),
        (3, 30003, 1, True, 123, trade("STALE")),
        (4, 30001, 1, True, 123, asset()), (5, 30003, 1, True, 123, trade("T2")),
    ])
    sent = []

    class Ring:
        def __init__(self, *a, **k):
            pass

        def receive(self, deadline):
            yield from frames

        def send(self, raw, deadline):
            sent.append(native.decode_frame(raw)[:2])

    monkeypatch.setattr(native, "_Ring", Ring)
    connection = native._WorkerConnection({"path": str(tmp_path), "account": "A",
                                          "session": 123, "owner": "owner", "timeout": 1})
    try:
        assert connection.query("asset_trades", 1)["trades"][0]["traded_id"] == "T1"
        assert connection.query("asset_trades", 1)["trades"][0]["traded_id"] == "T2"
        assert sent == [(1, 10001), (2, 20005), (3, 20007), (4, 20005), (5, 20007)]
    finally:
        connection.close()
