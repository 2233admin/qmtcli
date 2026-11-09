"""Persistent parent transport: fresh responses, failures and process ownership."""
import json
import queue
import subprocess

import pytest

from qmtcli import native_asset
from qmtcli.native_session import NativeSession


@pytest.fixture
def child(monkeypatch, tmp_path):
    (tmp_path / "up_queue_xtquant").touch()
    monkeypatch.setattr(native_asset, "_paths", lambda path: (tmp_path, tmp_path))
    monkeypatch.setattr(native_asset, "_validate_runtime", lambda path: None)

    class Process:
        instances = []
        mismatch = False
        stall = False
        pid = 12345

        def __init__(self, *args, **kwargs):
            self.output = queue.Queue()
            self.stdout = self
            self.stdin = self
            self.returncode = None
            self.requests = []
            self.instances.append(self)

        def write(self, line):
            request = json.loads(line)
            self.requests.append(request)
            if "owner" in request:
                response = {"ready": True}
            elif self.stall:
                return
            else:
                response = {"id": request["id"] + int(self.mismatch), "ok": True,
                            "data": {"asset": {"read": len(self.requests) - 1}, "trades": []}}
            self.output.put(native_asset.WORKER_MARKER + json.dumps(response) + "\n")

        def flush(self):
            pass

        def __iter__(self):
            return self

        def __next__(self):
            value = self.output.get(timeout=2)
            if value is None:
                raise StopIteration
            return value

        def poll(self):
            return self.returncode

        def close(self):
            self.returncode = 0
            self.output.put(None)

        def wait(self, timeout=None):
            self.returncode = 0
            return 0

    monkeypatch.setattr(subprocess, "Popen", Process)
    return Process


def test_native_worker_reused_but_results_are_fresh(child):
    session = NativeSession("SYNTHETIC", "A")
    try:
        first = session.query("asset", 1)
        second = session.query("asset", 1)
        assert [first["asset"]["read"], second["asset"]["read"]] == [1, 2]
        assert len(child.instances) == 1 and session.generation == 1
        assert [r.get("id") for r in child.instances[0].requests] == [None, 1, 2]
    finally:
        session.close()
    assert child.instances[0].returncode == 0


def test_mismatched_reply_fails_without_replay_then_later_request_restarts(child):
    session = NativeSession("SYNTHETIC", "A")
    child.mismatch = True
    with pytest.raises(RuntimeError, match="request"):
        session.query("asset", 1)
    assert len(child.instances) == 1 and child.instances[0].returncode == 0
    child.mismatch = False
    try:
        assert session.query("asset", 1)["asset"]["read"] == 1
        assert len(child.instances) == 2 and session.generation == 2
    finally:
        session.close()


def test_native_reply_timeout_never_returns_cached_data(child):
    session = NativeSession("SYNTHETIC", "A")
    assert session.query("asset", 1)
    child.stall = True
    with pytest.raises(TimeoutError):
        session.query("asset", 0.1)
    assert len(child.instances) == 1 and child.instances[0].returncode == 0


def test_rejects_non_read_operation_before_starting_child(child):
    session = NativeSession("SYNTHETIC", "A")
    with pytest.raises(ValueError):
        session.query("order", 1)
    assert not child.instances


def test_hung_worker_cleanup_targets_only_owned_process_tree(child, monkeypatch):
    session = NativeSession("SYNTHETIC", "A")
    session.query("asset", 1)
    process = child.instances[0]
    calls = []
    waits = []

    def wait(timeout=None):
        waits.append(timeout)
        if len(waits) == 1:
            raise subprocess.TimeoutExpired("synthetic-worker", timeout)
        return 0

    monkeypatch.setattr(process, "wait", wait)
    monkeypatch.setattr(subprocess, "run", lambda args, **kwargs: calls.append(args))
    session.close()
    assert waits == [1, 3]
    assert calls == [["taskkill", "/PID", str(process.pid), "/T", "/F"]]


def test_worker_crash_fails_current_read_without_replay(child, monkeypatch):
    session = NativeSession("SYNTHETIC", "A")
    session.query("asset", 1)
    process = child.instances[0]
    monkeypatch.setattr(process, "write", lambda line: process.output.put(None))
    with pytest.raises(RuntimeError, match="exited"):
        session.query("asset", 1)
    assert len(child.instances) == 1 and process.returncode == 0


@pytest.mark.parametrize("reply", [
    "{", "[]", '{"id":true,"ok":true,"data":{}}',
    '{"id":2,"ok":true,"data":[]}', '{"id":2,"ok":false,"error":"synthetic failure"}',
])
def test_invalid_worker_output_rejects_read_then_recovers(child, monkeypatch, reply):
    session = NativeSession("SYNTHETIC", "A")
    session.query("asset", 1)
    process = child.instances[0]
    monkeypatch.setattr(process, "write",
                        lambda line: process.output.put(native_asset.WORKER_MARKER + reply + "\n"))
    with pytest.raises(RuntimeError):
        session.query("asset", 1)
    assert process.returncode == 0 and session._process is None
    assert len(child.instances) == 1
    try:
        assert session.query("asset", 1)["asset"]["read"] == 1
        assert len(child.instances) == 2 and session.generation == 2
    finally:
        session.close()
