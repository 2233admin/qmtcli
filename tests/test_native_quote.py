"""Native quote transport/public boundary tests; no broker installation required."""
import io
import hashlib
import json
import os
import struct
import sys
import zlib

import pytest

from qmtcli.cli import _handle_rpc_request, main


def test_native_full_tick_cli_rpc_and_server_preserve_public_result(monkeypatch, capsys):
    from qmtcli import native_quote

    result = {"600000.SH": {"time": 123, "lastPrice": 9.5, "bidPrice": [9.4] * 5}}
    calls = []

    def query(path, symbols, timeout=5, port=58610):
        calls.append((path, symbols, timeout, port))
        return result

    monkeypatch.setattr(native_quote, "query_native_full_tick", query)
    assert main(["--path", "QMT", "full-tick", "600000.SH", "--backend", "native"]) == 0
    assert json.loads(capsys.readouterr().out) == result
    request = {"command": "full_tick", "backend": "native", "path": "QMT",
               "symbols": ["600000.SH"], "id": 7}
    assert _handle_rpc_request(request) == {"ok": True, "data": result, "id": 7}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(request) + "\n"))
    assert main(["server"]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "data": result, "id": 7}
    assert calls == [("QMT", ["600000.SH"], 5, 58610)] * 3


def test_native_failure_is_explicit_without_sdk_fallback(monkeypatch):
    from qmtcli import native_quote

    def fail(*args, **kwargs):
        raise ValueError("quote RPC CRC mismatch")

    monkeypatch.setattr(native_quote, "query_native_full_tick", fail)
    response = _handle_rpc_request({"command": "full-tick", "backend": "native", "path": "QMT",
                                    "symbols": ["600000.SH"], "id": "bad"})
    assert response == {"ok": False, "error": "quote RPC CRC mismatch", "id": "bad"}


class Codec:
    """Fixed BSON request fixture; response decoding supplied by each test."""
    @staticmethod
    def encode(doc):
        # Fixed empty params fixture; real parameter encoding is integration-tested
        # with the installed vendor codec, without adding a second BSON dependency.
        method = doc["func"].encode() + b"\0"
        body = b"\x02func\0" + struct.pack("<i", len(method)) + method
        body += b"\x03params\0\x05\0\0\0\0\0"
        return struct.pack("<i", len(body) + 4) + body


def packet(seq, payload=b"fixture", kind=3, flags=0x2042):
    body = zlib.compress(payload)
    if flags & 0x2000:
        body += struct.pack(">I", zlib.crc32(body, 0xffffffff))
    return struct.pack(">IIHH", len(body) + 12, seq, kind, flags) + body


class Socket:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.sent = []
        self.closed = False

    def settimeout(self, timeout):
        assert timeout > 0

    def recv(self, count):
        return next(self.chunks, b"")

    def sendall(self, data):
        self.sent.append(data)

    def close(self):
        self.closed = True


def test_named_bson_array_and_actual_pid_allowlist():
    from qmtcli.native_quote import encode_request

    raw = encode_request(Codec, 1, "authPid", {"pid": os.getpid()})
    size, seq, kind, flags = struct.unpack(">IIHH", raw[:12])
    assert (size, seq, kind, flags) == (len(raw), 1, 3, 0x42)
    decoded = zlib.decompress(raw[12:])
    assert b"\x04params\0" in decoded and b"\x03params\0" not in decoded
    with pytest.raises(ValueError, match="caller PID"):
        encode_request(Codec, 1, "authPid", {"pid": os.getpid() + 1})
    with pytest.raises(ValueError, match="read-only"):
        encode_request(Codec, 1, "supplyHistoryData2", {})


def test_fragmented_and_coalesced_frames_preserve_sequence():
    from qmtcli.native_quote import QuoteConnection

    class ReplyCodec(Codec):
        def __init__(self, raw):
            self.raw = raw

        def decode(self):
            return {"status": 0, "params": {"raw": self.raw}}

    first, second = packet(1, b"first"), packet(2, b"second")
    sock = Socket([first[:3], first[3:14], first[14:] + second])
    client = QuoteConnection(sock, ReplyCodec)
    assert client.request("authPid", {"pid": os.getpid()}, 10)["raw"] == b"first"
    assert client.request("getFullTick", {"stockMarkets": ["600000.SH"]}, 10)["raw"] == b"second"
    assert len(sock.sent) == 2


@pytest.mark.parametrize("raw,error", [
    (packet(1)[:-1] + b"x", "CRC"),
    (packet(2), "sequence"),
    (packet(1, kind=12), "unsupported"),
    (struct.pack(">IIHH", 5_000_000, 1, 3, 0x2042), "size"),
    (packet(1)[:15], "closed"),
    (packet(1, b"x" * (4 * 1024 * 1024 + 1)), "compressed"),
])
def test_corrupt_unsupported_and_unmatched_replies_fail(raw, error):
    from qmtcli.native_quote import QuoteConnection

    with pytest.raises((ValueError, EOFError), match=error):
        QuoteConnection(Socket([raw]), Codec).request("authPid", {"pid": os.getpid()}, 10)


@pytest.mark.parametrize("symbols,timeout,port", [
    ("600000.SH", 5, 58610), ([], 5, 58610), (["bad\0code"], 5, 58610),
    (["600000.SH"], True, 58610), (["600000.SH"], float("nan"), 58610),
    (["600000.SH"], 0, 58610), (["600000.SH"], 5, True),
    (["600000.SH"], 5, 65536),
])
def test_invalid_inputs_fail_before_connect(symbols, timeout, port):
    from qmtcli.native_quote import query_native_full_tick

    with pytest.raises(ValueError):
        query_native_full_tick("absent", symbols, timeout, port)


def test_query_closes_owned_socket_even_on_auth_rejection(monkeypatch):
    from qmtcli import native_quote

    class Rejected(Codec):
        def __init__(self, raw):
            pass

        def decode(self):
            return {"status": 0, "params": {"success": False}}

    sock = Socket([packet(1)])
    monkeypatch.setattr(native_quote, "load_codec", lambda path: Rejected)
    monkeypatch.setattr(native_quote.socket, "create_connection", lambda *a, **k: sock)
    with pytest.raises(RuntimeError, match="authentication"):
        native_quote.query_native_full_tick("QMT", ["600000.SH"])
    assert sock.closed


@pytest.mark.parametrize("reply,error", [
    ({"status": 1, "params": {}}, "rejected"),
    ({"status": 0, "params": {"result": []}}, "symbol mapping"),
    ({"status": 0, "params": {"result": {"UNREQUESTED": {}}}}, "symbol mapping"),
    ({"status": 0, "params": {"result": {"600000.SH": None}}}, "symbol mapping"),
])
def test_invalid_result_closes_socket_without_returning_partial_data(monkeypatch, reply, error):
    from qmtcli import native_quote

    responses = iter([{"status": 0, "params": {"success": True}}, reply])

    class Replies(Codec):
        def __init__(self, raw):
            pass

        def decode(self):
            return next(responses)

    sock = Socket([packet(1), packet(2)])
    monkeypatch.setattr(native_quote, "load_codec", lambda path: Replies)
    monkeypatch.setattr(native_quote.socket, "create_connection", lambda *a, **k: sock)
    with pytest.raises((RuntimeError, ValueError), match=error):
        native_quote.query_native_full_tick("QMT", ["600000.SH"])
    assert sock.closed


def test_empty_cache_is_success_and_connection_is_closed(monkeypatch):
    from qmtcli import native_quote

    responses = iter([{"status": 0, "params": {"success": True}},
                      {"status": 0, "params": {"result": {}}}])

    class Replies(Codec):
        def __init__(self, raw):
            pass

        def decode(self):
            return next(responses)

    sock = Socket([packet(1), packet(2)])
    monkeypatch.setattr(native_quote, "load_codec", lambda path: Replies)
    monkeypatch.setattr(native_quote.socket, "create_connection", lambda *a, **k: sock)
    assert native_quote.query_native_full_tick("QMT", ["600000.SH"]) == {}
    assert sock.closed


def test_expired_budget_does_not_send_request():
    from qmtcli.native_quote import QuoteConnection

    sock = Socket([])
    with pytest.raises(TimeoutError, match="deadline"):
        QuoteConnection(sock, Codec).request("authPid", {"pid": os.getpid()}, 0)
    assert sock.sent == []


def test_installed_codec_is_isolated_pure_python_and_runtime_changes_are_rejected(tmp_path, monkeypatch):
    from qmtcli import native_quote

    (tmp_path / "userdata_mini").mkdir()
    bin_dir = tmp_path / "bin.x64"
    codec_dir = bin_dir / "Lib/site-packages/xtquant/xtbson/bson37"
    codec_dir.mkdir(parents=True)
    (bin_dir / "miniquote.exe").write_bytes(b"fixture runtime")
    monkeypatch.setattr(native_quote, "PROFILES", {
        "miniquote.exe": hashlib.sha256(b"fixture runtime").hexdigest(),
    })
    monkeypatch.setattr(native_quote.sys, "platform", "win32")
    (codec_dir / "__init__.py").write_text(
        "try:\n from . import _cbson\n _USE_C=True\n"
        "except ImportError:\n _USE_C=False\nfrom .codec import BSON\n"
    )
    (codec_dir / "_cbson.py").write_text("raise AssertionError('compiled codec attempted')\n")
    (codec_dir / "codec.py").write_text("class BSON: pass\n")
    original_path, original_modules = list(sys.path), set(sys.modules)
    try:
        codec = native_quote.load_codec(str(tmp_path))
        assert codec is native_quote.load_codec(str(tmp_path / "userdata_mini"))
        name = codec.__module__.removesuffix(".codec")
        assert sys.modules[name]._USE_C is False
        assert sys.path == original_path
        assert not any(k.startswith("xtquant") for k in set(sys.modules) - original_modules)
        (bin_dir / "miniquote.exe").write_bytes(b"new version")
        with pytest.raises(ValueError, match="fingerprint"):
            native_quote.load_codec(str(tmp_path))
    finally:
        for name in set(sys.modules) - original_modules:
            if name.startswith("_qmtcli_quote_bson_"):
                del sys.modules[name]
