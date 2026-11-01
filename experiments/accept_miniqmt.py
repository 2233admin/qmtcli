"""Read-only MiniQMT Rust acceptance; omit identifiers, amounts and private records.

The optional development runner uses installed psutil for owned-worker checks.
The Rust executable itself has no Python dependency. No service is started here.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


def summarize_snapshot(data, account):
    if not isinstance(data, dict) or not isinstance(data.get("asset"), dict):
        raise ValueError("incomplete snapshot")
    counts = {}
    for section in ("positions", "orders", "trades"):
        rows = data.get(section)
        if not isinstance(rows, list):
            raise ValueError("incomplete snapshot")
        if any(not isinstance(row, dict) or row.get("account_id") != account for row in rows):
            raise ValueError("snapshot record identity mismatch")
        counts[section] = len(rows)
    asset = data["asset"]
    if asset.get("account_id") != account:
        raise ValueError("snapshot asset identity mismatch")
    for field in ("cash", "frozen_cash", "market_value", "total_asset"):
        number = asset.get(field)
        if type(number) not in (int, float) or not math.isfinite(number):
            raise ValueError("snapshot asset amounts must be finite")
    meta = data.get("meta", {})
    generation = meta.get("native_generation")
    if type(generation) is not int or generation < 1:
        raise ValueError("snapshot native generation missing or invalid")
    if meta.get("atomic") is not False or meta.get("event_sequence_available") is not False:
        raise ValueError("snapshot consistency markers invalid")
    return {
        "counts": counts,
        "asset_amounts_finite": True,
        "account_identity_matched": True,
        "native_generation": generation,
        "atomic": False,
        "event_sequence_available": False,
    }


class Client:
    def __init__(self, exe):
        import psutil

        self.psutil = psutil
        env = dict(os.environ)
        env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
        self.process = subprocess.Popen(
            [str(exe.resolve()), "server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding="utf-8", env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.lines = queue.Queue()
        self.serial = 0
        self.workers = {}
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(32 * 1024 * 1024 + 1)
                if not line or len(line) > 32 * 1024 * 1024:
                    break
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def call(self, request, expect_ok=True):
        self.serial += 1
        self.process.stdin.write(json.dumps({**request, "id": self.serial}) + "\n")
        self.process.stdin.flush()
        line = self.lines.get(timeout=20)
        if line is None:
            raise ValueError("Rust CLI exited before replying")
        reply = json.loads(line)
        if reply.get("id") != self.serial or reply.get("ok") is not expect_ok:
            # Never copy an error message or a returned private record into a receipt.
            raise ValueError("Rust CLI response did not match the requested phase")
        return reply.get("data")

    def observe_workers(self):
        children = self.psutil.Process(self.process.pid).children()
        if not children:
            raise ValueError("native worker missing")
        for worker in children:
            worker.create_time()
            self.workers[worker.pid] = worker

    def close(self):
        self.process.stdin.close()
        try:
            code = self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
            code = -1
        self.reader.join(timeout=2)
        self.process.stdout.close()
        _, alive = self.psutil.wait_procs(list(self.workers.values()), timeout=5)
        return code == 0 and not alive


def run(args, report):
    root = args.path.resolve()
    data = root if root.name == "userdata_mini" else root / "userdata_mini"
    report["account_service_queue_present"] = (data / "up_queue_xtquant").is_file()
    if not report["account_service_queue_present"]:
        report.update(status="blocked", reason="MiniQMT account service queue is missing")
        return 2
    account = os.environ.get(args.account_env)
    if not account:
        report.update(status="blocked", reason="Set the selected account environment variable")
        return 2
    report["exe_sha256"] = hashlib.sha256(args.exe.read_bytes()).hexdigest()
    base = {"backend": "native", "path": str(root), "account": account, "timeout": 5}
    quote = {"command": "full-tick", "backend": "native", "path": str(root),
             "symbols": ["600000.SH", "000001.SZ"], "quote_port": args.quote_port, "timeout": 5}
    client = Client(args.exe)
    try:
        report["phase"] = "doctor"
        doctor = client.call({"command": "doctor", "path": str(root)})
        if doctor.get("quote_profile") != "matched" or doctor.get("account_profile") != "matched":
            raise ValueError("installed runtime profile mismatch")
        report["phase"] = "snapshots"
        snapshots = []
        for _ in range(args.snapshots):
            snapshots.append(summarize_snapshot(client.call({**base, "command": "account-snapshot"}), account))
        if len({row["native_generation"] for row in snapshots}) != 1:
            raise ValueError("account session was not retained")
        client.observe_workers()
        report["snapshots"] = snapshots
        report["phase"] = "input_rejection"
        client.call({**base, "command": "asset", "account_type": "CREDIT"}, expect_ok=False)
        recovered = summarize_snapshot(client.call({**base, "command": "account-snapshot"}), account)
        if recovered["native_generation"] != snapshots[0]["native_generation"]:
            raise ValueError("input validation discarded the healthy session")
        report["input_rejection_kept_session"] = True
        report["phase"] = "quote"
        first_tick = client.call(quote)
        for code in quote["symbols"]:
            if not isinstance(first_tick.get(code), dict) or not first_tick[code].get("time"):
                raise ValueError("quote cache timestamp missing")
        report["quote_times"] = {code: first_tick[code]["time"] for code in quote["symbols"]}
        report["phase"] = "idle"
        until = time.monotonic() + args.idle_seconds
        while (remaining := until - time.monotonic()) > 0:
            time.sleep(min(30, remaining))
        client.call(quote)
        after_idle = summarize_snapshot(client.call({**base, "command": "account-snapshot"}), account)
        if after_idle["native_generation"] != snapshots[0]["native_generation"]:
            raise ValueError("account session changed during idle")
        status = client.call({"command": "status"})
        if status.get("quote_session_connected") is not True or status.get("account_transport_available") is not True:
            raise ValueError("independent retained sessions unavailable")
        report["idle_seconds"] = args.idle_seconds
        report["independent_sessions_retained"] = True
        report["phase"] = "cleanup"
    finally:
        report["owned_processes_closed"] = client.close()
    if not report["owned_processes_closed"]:
        raise ValueError("owned process cleanup failed")
    report.update(status="passed", passed=True)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--scope", choices=("actual-miniqmt", "synthetic"), required=True)
    parser.add_argument("--account-env", default="QMTCLI_ACCOUNT")
    parser.add_argument("--quote-port", type=int, default=58610)
    parser.add_argument("--snapshots", type=int, choices=range(2, 41), default=2)
    parser.add_argument("--idle-seconds", type=float, default=0)
    args = parser.parse_args()
    if not 0 <= args.idle_seconds <= 120 or not 1 <= args.quote_port <= 65535:
        parser.error("idle must be 0..120 seconds; port must be 1..65535")
    report = {"passed": False, "scope": args.scope, "read_only": True,
              "private_account_records_persisted": False, "system32_only_child_path": True,
              "coverage": "four-section reads/reuse/idle/EOF; not event or forced broker-disconnect acceptance"}
    try:
        code = run(args, report)
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__)
        code = 1
    args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
