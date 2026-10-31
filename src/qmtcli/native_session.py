"""Owned persistent native worker, shared only by sequential account requests."""
from __future__ import annotations

import json
import math
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

from qmtcli import native_asset as transport


class NativeSession:
    def __init__(self, path: str, account: str, account_type: str = "STOCK"):
        transport.encode_account(account, account_type)
        self.path, self.account = path, account
        self.generation = 0
        self._process = None
        self._reply = None
        self._reader = None
        self._messages = queue.Queue()
        self._request = 0
        self._lock = threading.RLock()

    @staticmethod
    def _read_output(process, messages) -> None:
        try:
            for line in process.stdout:
                if line.startswith(transport.WORKER_MARKER):
                    messages.put(json.loads(line[len(transport.WORKER_MARKER):]))
        except Exception:
            messages.put(RuntimeError("native worker returned invalid output"))
        finally:
            messages.put(RuntimeError("native worker exited before its reply"))

    def _receive(self, deadline: float) -> dict:
        try:
            value = self._messages.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty as exc:
            raise TimeoutError("native worker response deadline exceeded") from exc
        if isinstance(value, Exception):
            raise value
        if not isinstance(value, dict):
            raise RuntimeError("native worker returned invalid response")
        return value

    def _start(self, data: Path, deadline: float) -> None:
        if self._process is not None and self._process.poll() is None:
            return
        self.close()
        session, owner, self._reply = transport._reserve_reply(data)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
        self._messages = queue.Queue()
        self._process = subprocess.Popen(
            [sys.executable, "-m", "qmtcli.native_asset", "--server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.generation += 1
        self._reader = threading.Thread(target=self._read_output,
                                        args=(self._process, self._messages), daemon=True)
        self._reader.start()
        self._send({"path": str(data), "account": self.account, "session": session,
                    "owner": owner, "timeout": max(0.001, deadline - time.monotonic())})
        ready = self._receive(deadline)
        if ready.get("ready") is not True:
            raise RuntimeError(ready.get("error", "native worker did not initialize"))

    def _send(self, request: dict) -> None:
        self._process.stdin.write(json.dumps(request) + "\n")
        self._process.stdin.flush()

    def query(self, operation: str, timeout: float = 5) -> dict:
        if operation not in {"asset", "asset_trades"}:
            raise ValueError("unsupported native read operation")
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or not 0 < timeout <= 60):
            raise ValueError("native response timeout must be positive and at most 60 seconds")
        with self._lock:
            try:
                data, bin_dir = transport._paths(self.path)
                transport._validate_runtime(bin_dir)
                if operation == "asset_trades":
                    from qmtcli.native_trades import validate_trade_runtime
                    validate_trade_runtime(bin_dir)
                if not (data / "up_queue_xtquant").is_file():
                    raise RuntimeError("MiniQMT native service queue is missing")
                deadline = time.monotonic() + timeout
                self._start(data, deadline)
                self._request += 1
                self._send({"id": self._request, "operation": operation,
                            "timeout": max(0.001, deadline - time.monotonic())})
                response = self._receive(deadline)
                if type(response.get("id")) is not int or response["id"] != self._request:
                    raise RuntimeError("native worker response does not match request")
                if response.get("ok") is not True or not isinstance(response.get("data"), dict):
                    raise RuntimeError(response.get("error", "native worker returned invalid data"))
                return response["data"]
            except BaseException:
                self.close()
                raise

    def close(self) -> None:
        with self._lock:
            process, self._process = self._process, None
            try:
                if process is not None:
                    try:
                        process.stdin.close()
                    except (BrokenPipeError, OSError):
                        pass
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        # A Windows launcher can own a child interpreter. Kill only
                        # this Popen-owned process tree, never shared QMT processes.
                        if os.name == "nt":
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                           timeout=3, creationflags=subprocess.CREATE_NO_WINDOW)
                        else:
                            process.kill()
                        process.wait(timeout=3)
                    process.stdout.close()
                if self._reader is not None:
                    self._reader.join(timeout=1)
            finally:
                self._reader = None
                if self._reply is not None:
                    transport._remove_reply(self._reply)
                    self._reply = None
