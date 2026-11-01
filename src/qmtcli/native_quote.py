"""Pinned MiniQMT full-tick RPC without importing xtquant or its CPython extensions.

Only normal caller-PID authentication and one read operation are exposed. Each
query owns a bounded local connection; quote subscription/idle frames are not yet
part of this adapter's contract. BSON comes from the installed pure-Python codec.
"""
from __future__ import annotations

import hashlib
import importlib.util
import math
import os
import socket
import struct
import sys
import threading
import time
import zlib

HEADER = struct.Struct(">IIHH")
MAX_SIZE = 4 * 1024 * 1024
PROFILES = {
    "miniquote.exe": "1bfd04220c7635d22ae81a2e70e40c09cb7192aa51ba90c1e6b6ec1859c76ade",
    "QuoteCenter_mini.dll": "a2154c07b097aa7daf8b8f9528f4f039135d585a4968ae5b4f1e2315afd02925",
    "quoter.dll": "e1cc4b1819b2c9d9490ef83e0e906e680f45c8fa6bb314a350373196e22f1015",
    "net.dll": "2cd891348d3f504e342b71109fc8753a3ca261bb7658f7105a6cee31c6a91aff",
    "utils.dll": "fa55c69e4d8a0b449894dcf8bf767dd03e2c0cdc6b33727e0530445950fd14a8",
}
_CODEC_LOCK = threading.Lock()


def load_codec(path: str):
    """Reuse the broker's BSON implementation under a private package namespace.

    Relative imports keep sys.path and the xtquant import namespace untouched.
    Blocking _cbson deliberately selects the vendor's pure-Python implementation.
    """
    from qmtcli.native_asset import _paths

    _, bin_dir = _paths(path)
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("native quote requires Windows x64")
    for name, expected in PROFILES.items():
        if hashlib.sha256((bin_dir / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"unsupported native quote runtime: {name} fingerprint mismatch")
    init = bin_dir / "Lib/site-packages/xtquant/xtbson/bson37/__init__.py"
    name = "_qmtcli_quote_bson_" + hashlib.sha256(str(init).encode()).hexdigest()[:16]
    with _CODEC_LOCK:
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, init)
            if spec is None or spec.loader is None:
                raise RuntimeError("installed pure-Python BSON codec unavailable")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            sys.modules[name + "._cbson"] = None
            try:
                spec.loader.exec_module(module)
            except Exception:
                for key in list(sys.modules):
                    if key == name or key.startswith(name + "."):
                        del sys.modules[key]
                raise
        return sys.modules[name].BSON


def encode_request(codec, seq: int, method: str, params: dict) -> bytes:
    if method not in {"authPid", "getFullTick"}:
        raise ValueError("native quote is read-only: method is not allowed")
    if method == "authPid" and params != {"pid": os.getpid()}:
        raise ValueError("authentication requires the real caller PID")
    encoded = codec.encode({"func": method, "params": params})
    # The native server requires named elements inside a BSON array. The codec
    # encodes its contents; only this known top-level container tag is changed.
    offset = 15 + len(method)
    if encoded[offset:offset + 8] != b"\x03params\0":
        raise ValueError("unexpected BSON request container")
    encoded = encoded[:offset] + b"\x04" + encoded[offset + 1:]
    body = zlib.compress(encoded)
    flags = 0x42 if method == "authPid" else 0x2042
    if flags & 0x2000:
        body += struct.pack(">I", zlib.crc32(body, 0xffffffff))
    if len(body) + HEADER.size > MAX_SIZE:
        raise ValueError("native quote request size exceeds limit")
    return HEADER.pack(HEADER.size + len(body), seq, 3, flags) + body


def _decode_body(codec, raw: bytes, flags: int) -> dict:
    if flags & 0x2000:
        if len(raw) < 4 or struct.unpack(">I", raw[-4:])[0] != zlib.crc32(raw[:-4], 0xffffffff):
            raise ValueError("quote RPC CRC mismatch")
        raw = raw[:-4]
    unpack = zlib.decompressobj()
    payload = unpack.decompress(raw, MAX_SIZE + 1)
    if len(payload) > MAX_SIZE or not unpack.eof or unpack.unused_data:
        raise ValueError("invalid compressed quote RPC payload")
    response = codec(payload).decode()
    if (not isinstance(response, dict) or type(response.get("status")) is not int
            or response["status"] != 0 or not isinstance(response.get("params"), dict)):
        raise RuntimeError("native quote service rejected request or returned an invalid reply")
    return response["params"]


class QuoteConnection:
    """Single-owner frame reader; no retries, SDK fallback or push subscriptions."""

    def __init__(self, sock, codec):
        self.sock, self.codec = sock, codec
        self.seq = 0
        self.buffer = bytearray()

    def _read(self, deadline: float) -> dict:
        while True:
            if len(self.buffer) >= HEADER.size:
                size, seq, kind, flags = HEADER.unpack_from(self.buffer)
                if not HEADER.size <= size <= MAX_SIZE:
                    raise ValueError("invalid quote RPC frame size")
                if kind != 3 or flags not in (0x42, 0x2042):
                    raise ValueError("unsupported quote RPC frame kind/flags")
                if seq != self.seq:
                    raise ValueError("quote RPC reply sequence mismatch")
                if len(self.buffer) >= size:
                    body = bytes(self.buffer[HEADER.size:size])
                    del self.buffer[:size]
                    return _decode_body(self.codec, body, flags)
            self.sock.settimeout(_remaining(deadline))
            part = self.sock.recv(65536)
            if not part:
                raise EOFError("native quote connection closed before reply")
            self.buffer.extend(part)

    def request(self, method: str, params: dict, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        self.seq += 1
        packet = encode_request(self.codec, self.seq, method, params)
        self.sock.settimeout(_remaining(deadline))
        self.sock.sendall(packet)
        return self._read(deadline)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("native quote response deadline exceeded")
    return remaining


def _validate_inputs(symbols, timeout, port):
    if (not isinstance(symbols, list) or not 1 <= len(symbols) <= 1000
            or any(not isinstance(s, str) or not 1 <= len(s) <= 64
                   or not s.isascii() or not s.isprintable() or any(c.isspace() for c in s)
                   for s in symbols)):
        raise ValueError("native full-tick requires 1 to 1000 nonempty ASCII symbols")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0.1 <= timeout <= 60):
        raise ValueError("native quote timeout must be between 0.1 and 60 seconds")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("quote_port must be an integer between 1 and 65535")


def query_native_full_tick(path: str, symbols: list[str], timeout: float = 5,
                           port: int = 58610) -> dict:
    """Return the SDK-compatible symbol mapping, preserving server timestamps.

    Timeout bounds connect + auth + query; local profile/codec loading precedes
    that budget. Empty mappings are legitimate cached-data results.
    """
    _validate_inputs(symbols, timeout, port)
    codec = load_codec(path)
    deadline = time.monotonic() + timeout
    sock = socket.create_connection(("127.0.0.1", port), timeout=_remaining(deadline))
    try:
        client = QuoteConnection(sock, codec)
        if client.request("authPid", {"pid": os.getpid()}, _remaining(deadline)).get("success") is not True:
            raise RuntimeError("native quote caller-PID authentication rejected")
        reply = client.request("getFullTick", {"stockMarkets": symbols}, _remaining(deadline))
        result = reply.get("result")
        if (not isinstance(result, dict) or any(key not in symbols or not isinstance(value, dict)
                                               for key, value in result.items())):
            raise ValueError("invalid native full-tick symbol mapping")
        return result
    finally:
        sock.close()
