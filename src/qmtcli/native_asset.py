"""Version-pinned, read-only MiniQMT asset/trade IPC without CPython SDK extensions.

The ringbuffer runtime is vendor C++, so native calls run only in a bounded child
process. This module's codecs and parent adapter are usable without that library.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
import time

HEADER = struct.Struct("<QIBB2xQ")
ACCOUNT = struct.Struct("<i24s")
ASSET = struct.Struct("<i24s6d")
CONNECT, ASSET_QUERY, TRADES_QUERY = 10001, 20005, 20007
WORKER_MARKER = "QMTCLI_NATIVE_RESULT:"
PROFILES = {
    "ringbuffer.dll": "b40def1af839286baaf6b8bdcde7c88a0c555dbfb56d9bb3592661db84922c48",
    "XtQuantServer.dll": "6dc0474701691e5be22d501f92cc36c75e13d9f24781debc69fe90dfaf4b4050",
}


def encode_account(account: str, account_type: str) -> bytes:
    if not isinstance(account_type, str) or account_type.upper() != "STOCK":
        raise ValueError("native asset currently supports STOCK accounts only")
    if (not isinstance(account, str) or not account or not account.isascii()
            or not account.isprintable() or account.isspace()):
        raise ValueError("account must be nonempty printable ASCII without control characters")
    if len(account) > 23:
        raise ValueError("account exceeds the native 23-byte limit")
    return ACCOUNT.pack(2, account.encode("ascii"))


def encode_frame(seq: int, kind: int, session: int, body: bytes, bucket_size: int = 512) -> bytes:
    if kind not in (CONNECT, ASSET_QUERY, TRADES_QUERY):
        raise ValueError("native asset is read-only: request type is not allowed")
    if not 0 < seq < 2**64 or not 0 < session < 2**63:
        raise ValueError("invalid native sequence/session")
    if len(body) != (12 if kind == CONNECT else ACCOUNT.size):
        raise ValueError("invalid native request body length")
    packet = HEADER.pack(seq, kind, 0, 1, session) + body
    if len(packet) > bucket_size:
        raise ValueError("request exceeds native bucket size")
    return packet.ljust(bucket_size, b"\0")


def decode_frame(raw: bytes) -> tuple:
    if len(raw) < HEADER.size:
        raise ValueError("truncated native header")
    seq, kind, action, last, session = HEADER.unpack_from(raw)
    if action not in (0, 1, 2) or last not in (0, 1):
        raise ValueError("invalid native message action/last flag")
    return seq, kind, action, bool(last), session, raw[HEADER.size:]


def decode_asset(raw: bytes, expected_account: str) -> dict:
    if len(raw) < ASSET.size:
        raise ValueError("native asset response is shorter than 76 bytes")
    account_type, encoded, *values = ASSET.unpack_from(raw)
    account = encoded.split(b"\0", 1)[0].decode("ascii")
    if account_type != 2 or account != expected_account:
        raise ValueError("native asset response does not match requested account/type")
    public = dict(zip(("cash", "frozen_cash", "market_value", "total_asset"), values[:4]))
    if not all(math.isfinite(v) for v in public.values()):
        raise ValueError("native asset values must be finite")
    return {"account_type": account_type, "account_id": account, **public}


def _paths(path: str) -> tuple[Path, Path]:
    given = Path(path).resolve()
    data = given if given.name == "userdata_mini" else given / "userdata_mini"
    if not data.is_dir():
        raise ValueError("native backend requires an existing MiniQMT root or userdata_mini path")
    return data, data.parent / "bin.x64"


def _validate_runtime(bin_dir: Path) -> None:
    if sys.platform != "win32" or struct.calcsize("P") != 8:
        raise RuntimeError("native asset requires Windows x64")
    for name, expected in PROFILES.items():
        source = bin_dir / name
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise RuntimeError(f"unsupported native MiniQMT build: {name} fingerprint mismatch")


def query_native_asset(path: str, account: str, account_type: str = "STOCK", timeout: float = 5) -> dict:
    """Query once in a crash-isolated worker; never fall back to SDK/cache data."""
    return _query_native(path, account, account_type, timeout, operation="asset")


def _query_native(path: str, account: str, account_type: str, timeout: float, operation: str) -> dict:
    encode_account(account, account_type)
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0.1 <= timeout <= 60):
        raise ValueError("native timeout must be between 0.1 and 60 seconds")
    data, bin_dir = _paths(path)
    _validate_runtime(bin_dir)
    if operation == "asset_trades":
        from qmtcli.native_trades import validate_trade_runtime
        validate_trade_runtime(bin_dir)
    elif operation != "asset":
        raise ValueError("unsupported native read operation")
    if not (data / "up_queue_xtquant").is_file():
        raise RuntimeError("MiniQMT native service queue is missing; start and log in to MiniQMT")
    session = secrets.randbelow(2**31 - 1) + 1
    reply = data / f"down_queue_{session}"
    owner = secrets.token_hex(16)
    # Exclusive creation establishes ownership: never overwrite or unlink an existing session.
    with reply.open("xb") as reservation:
        reservation.write(("qmtcli-native-owner:" + owner).encode("ascii"))
    try:
        env = os.environ.copy()
        package_root = str(Path(__file__).resolve().parent.parent)
        env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
        request = {"path": str(data), "account": account, "session": session,
                   "timeout": timeout, "owner": owner, "operation": operation}
        try:
            result = subprocess.run(
                [sys.executable, "-m", "qmtcli.native_asset"],
                input=json.dumps(request), capture_output=True, text=True, encoding="utf-8",
                timeout=timeout + 3, env=env,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError("native asset worker exceeded its deadline") from exc
        if result.returncode:
            raise RuntimeError(f"native asset worker failed (exit {result.returncode})")
        response = _parse_worker_output(result.stdout)
        if not response.get("ok"):
            raise RuntimeError(response.get("error", "native asset query failed"))
        return response["data"]
    finally:
        try:
            reply.unlink()
        except (PermissionError, FileNotFoundError):
            # The broker can retain its writer mapping until it observes worker exit.
            pass


def _parse_worker_output(output: str) -> dict:
    # The vendor runtime can write diagnostics at process teardown. Its stdout is
    # captured here; only our marked response reaches the public JSON transport.
    messages = [line[len(WORKER_MARKER):] for line in output.splitlines()
                if line.startswith(WORKER_MARKER)]
    try:
        if len(messages) != 1:
            raise ValueError("expected exactly one result")
        response = json.loads(messages[0])
        if not isinstance(response, dict) or not isinstance(response.get("ok"), bool):
            raise ValueError("invalid envelope")
        return response
    except (ValueError, TypeError) as exc:
        raise RuntimeError("native worker returned invalid JSON") from exc


class _Ring:
    """Private x64 primitive ABI adapter; lifetime is the one-shot worker process."""

    def __init__(self, library, path: Path, create: bool = False):
        import ctypes as c
        import mmap

        self.c = c
        self.library = library
        self.file = path.open("r+b")
        if create:
            # Match the legacy file-backed session queues created by this SDK
            # build, including its shared semaphore strategy and slot capacity.
            self.file.truncate(75497752)
        self.mapping = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_WRITE)
        self.buffer = (c.c_char * len(self.mapping)).from_buffer(self.mapping)
        address = c.addressof(self.buffer)
        size = c.c_uint64(len(self.mapping))
        self.obj = c.c_void_p()
        if create:
            name = ("?create@RingBufferWriter@ringbuffer@base@@SA?AV?$unique_ptr@VRingBufferWriter@"
                    "ringbuffer@base@@U?$default_delete@VRingBufferWriter@ringbuffer@base@@@std@@@"
                    "std@@PEAXPEA_K_J2W4IOType@23@3W4WaitStrategyType@23@@Z")
            fn = self._bind(name, c.c_void_p, c.POINTER(c.c_void_p), c.c_void_p,
                            c.POINTER(c.c_uint64), c.c_int64, c.c_int64, c.c_int, c.c_int, c.c_int)
            fn(c.byref(self.obj), address, c.byref(size), 512, 131072, 1, 0, 2)
        else:
            if (len(self.mapping) < 75497752
                    or self.mapping[:8] != b"Head\0\0\0\0"
                    or struct.unpack_from("<5Q", self.mapping, 8) != (512, 131072, 1, 0, 2)):
                raise RuntimeError("invalid native queue header")
            name = ("?resume@RingBufferWriter@ringbuffer@base@@SA?AV?$unique_ptr@VRingBufferWriter@"
                    "ringbuffer@base@@U?$default_delete@VRingBufferWriter@ringbuffer@base@@@std@@@"
                    "std@@PEAXPEA_K@Z")
            fn = self._bind(name, c.c_void_p, c.POINTER(c.c_void_p), c.c_void_p,
                            c.POINTER(c.c_uint64))
            fn(c.byref(self.obj), address, c.byref(size))
        if not self.obj.value:
            raise RuntimeError("native ringbuffer could not initialize queue")
        self.get = self._bind("?get@RingBufferWriter@ringbuffer@base@@QEAAPEAX_J@Z",
                              c.c_void_p, c.c_void_p, c.c_int64)
        self.claim = self._bind("?tryClaim@RingBufferWriter@ringbuffer@base@@QEAA_NPEA_J@Z",
                                c.c_bool, c.c_void_p, c.POINTER(c.c_int64))
        self.commit = self._bind("?commit@RingBufferWriter@ringbuffer@base@@QEAAX_J@Z",
                                 None, c.c_void_p, c.c_int64)
        self.current = self._bind("?current@RingBufferReader@ringbuffer@base@@QEBA_JXZ",
                                  c.c_int64, c.c_void_p)
        self.wait = self._bind("?tryWaitFor@RingBufferReader@ringbuffer@base@@QEAA_N_JPEA_J@Z",
                               c.c_bool, c.c_void_p, c.c_int64, c.POINTER(c.c_int64))
        self.finish = self._bind("?finish@RingBufferReader@ringbuffer@base@@QEAAX_J@Z",
                                 None, c.c_void_p, c.c_int64)

    def _bind(self, name, result, *args):
        fn = getattr(self.library, name)
        fn.restype, fn.argtypes = result, list(args)
        return fn

    def send(self, raw: bytes, deadline: float) -> None:
        sequence = self.c.c_int64()
        while time.monotonic() < deadline:
            if self.claim(self.obj, self.c.byref(sequence)):
                self.c.memmove(self.get(self.obj, sequence.value), raw, len(raw))
                self.commit(self.obj, sequence.value)
                return
            time.sleep(0.001)
        raise TimeoutError("native service input queue is full")

    def receive(self, deadline: float):
        available = self.c.c_int64()
        while time.monotonic() < deadline:
            sequence = self.current(self.obj) + 1
            if self.wait(self.obj, sequence, self.c.byref(available)):
                raw = self.c.string_at(self.get(self.obj, sequence), 512)
                self.finish(self.obj, sequence)
                yield decode_frame(raw)
            else:
                time.sleep(0.001)


def _worker(request: dict) -> dict:
    import ctypes as c

    data, bin_dir = _paths(request["path"])
    _validate_runtime(bin_dir)
    operation = request.get("operation", "asset")
    trades = None
    if operation == "asset_trades":
        from qmtcli.native_trades import TradeReplies, validate_trade_runtime
        validate_trade_runtime(bin_dir)
        trades = TradeReplies(request["account"], int(request["session"]))
    elif operation != "asset":
        raise ValueError("unsupported native read operation")
    account = request["account"]
    account_raw = encode_account(account, "STOCK")
    session = int(request["session"])
    deadline = time.monotonic() + float(request["timeout"])
    reserved_reply = data / f"down_queue_{session}"
    marker = ("qmtcli-native-owner:" + request["owner"]).encode("ascii")
    # Check the parent's reservation before the native factory can truncate a
    # file. A directly invoked worker must not attach to an existing SDK session.
    if reserved_reply.stat().st_size != len(marker) or reserved_reply.read_bytes() != marker:
        raise RuntimeError("native reply queue is not owned by this worker")
    directory = os.add_dll_directory(str(bin_dir))
    library = c.WinDLL(str(bin_dir / "ringbuffer.dll"), winmode=0x1100)
    reply = _Ring(library, reserved_reply, create=True)
    outgoing = _Ring(library, data / "up_queue_xtquant")
    outgoing.send(encode_frame(1, CONNECT, session, struct.pack("<qi", session, os.getpid())), deadline)
    connected = False
    for seq, kind, action, last, source, body in reply.receive(deadline):
        if source != session:
            raise RuntimeError("native response belongs to another session")
        if trades is not None and connected and seq in (2, 3):
            rows = trades.feed((seq, kind, action, last, source, body))
            if rows is not None:
                directory.close()
                return {"asset": trades.asset, "trades": rows}
            if seq == 2 and kind == 30001:
                outgoing.send(encode_frame(3, TRADES_QUERY, session, account_raw), deadline)
            continue
        if kind == 20000:
            raise RuntimeError("MiniQMT rejected the native connection or query")
        if kind == 10002 and seq == 1 and not connected:
            if (action != 1 or not last or len(body) < 8
                    or struct.unpack_from("<q", body)[0] != session):
                raise RuntimeError("invalid native connection acknowledgement")
            connected = True
            outgoing.send(encode_frame(2, ASSET_QUERY, session, account_raw), deadline)
        elif kind == 30001 and seq == 2 and connected and action == 1 and last:
            result = decode_asset(body, account)
            directory.close()
            return result
    kind = "account" if trades is not None else "asset"
    raise TimeoutError(f"MiniQMT native {kind} response timed out")


if __name__ == "__main__":
    try:
        value = _worker(json.load(sys.stdin))
        print(WORKER_MARKER + json.dumps({"ok": True, "data": value}, ensure_ascii=False))
    except Exception as error:
        print(WORKER_MARKER + json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
