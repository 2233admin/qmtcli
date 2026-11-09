"""Read-only acceptance through a packaged Rust CLI and an already running Big QMT.

Uses only the three public formula commands; never starts a strategy or account API.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    base = {"backend": "formula", "path": args.path}
    symbols = ["000001.SZ", "600000.SH"]
    requests = [
        {"command": "doctor", **base},
        {"command": "instrument-detail", **base, "symbols": symbols[:1]},
        {"command": "daily-bars", **base, "symbols": symbols, "count": 2},
        {"command": "full-tick", **base, "symbols": symbols},
        {"command": "daily-bars", **base, "symbols": symbols, "count": 0},
        {"command": "status"},
        {"command": "full-tick", **base, "symbols": symbols},
        {"command": "capabilities"},
        {"command": "schema"},
        {"command": "examples"},
    ]
    for i, request in enumerate(requests):
        request["id"] = i
    env = dict(os.environ)
    env["PATH"] = str(Path(os.environ["SystemRoot"]) / "System32")
    child = subprocess.Popen(
        [str(args.exe.resolve()), "server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
    )
    try:
        stdout, stderr = child.communicate(
            "".join(json.dumps(r) + "\n" for r in requests), timeout=45
        )
    except subprocess.TimeoutExpired:
        child.kill()
        child.communicate()
        raise
    rows = [json.loads(line) for line in stdout.splitlines()]
    report = {
        "scope": "actual Big QMT public reads; client cache, not live freshness",
        "exe_sha256": hashlib.sha256(args.exe.read_bytes()).hexdigest(),
        "pid": child.pid,
        "exit_code": child.returncode,
        "system32_only_path": True,
        "stderr": stderr,
        "requests": requests,
        "responses": rows,
        "passed": False,
    }
    try:
        assert child.returncode == 0 and not stderr
        assert len(rows) == len(requests)
        assert all(row["id"] == i for i, row in enumerate(rows))
        assert all(row["ok"] == (i != 4) for i, row in enumerate(rows))
        assert rows[0]["data"]["formula_profile"] == "matched"
        instrument = rows[1]["data"]["data"]["instrument"]
        assert instrument["InstrumentID"] == "000001"
        assert instrument["ExchangeID"] == "SZ"
        for i in [1, 2, 3, 6]:
            meta = rows[i]["data"]["meta"]
            assert meta["source"] == "client-cache" and meta["realtime"] is False
            assert meta["freshness"] == "unknown"
        for symbol in symbols:
            bars = rows[2]["data"]["data"][symbol]
            assert 0 < len(bars) <= 2
            for bar in bars:
                assert len(bar["time"]) == 8
                assert set(bar["fields"]) == {
                    "open", "high", "low", "close", "volume", "amount"
                }
                assert bar["fields"]["close"] > 0
            tick = rows[3]["data"]["data"][symbol]
            assert len(tick) == 1 and tick[0]["fields"]["lastPrice"] > 0
        assert rows[5]["data"]["formula_session_connected"] is True
        assert rows[5]["data"]["quote_session_connected"] is False
        report["passed"] = True
    finally:
        args.receipt.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps({"passed": True, "requests": len(rows), "receipt": str(args.receipt)}))


if __name__ == "__main__":
    main()
