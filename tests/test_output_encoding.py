"""Output encoding contract: CLI bytes on stdout/stderr are UTF-8 regardless of host locale.

The agent contract (README/AGENTS.md) promises UTF-8 JSON on stdout. On zh-CN Windows,
Python's stdio otherwise defaults to the ANSI code page (GBK), silently emitting
non-RFC-8259 bytes for every Chinese string. main() reconfigures both streams; this test
pins that behaviour by forcing a GBK stdio default in a subprocess and decoding the raw
pipe bytes as UTF-8.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parents[1] / "src")


def test_cli_stdout_is_utf8_even_when_stdio_defaults_to_gbk() -> None:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "gbk"  # simulate a zh-CN Windows console on any platform
    env["PYTHONPATH"] = _SRC + os.pathsep + env.get("PYTHONPATH", "")
    script = (
        "import sys\n"
        "from qmtcli.cli import main\n"
        "rc = main(['fields'])\n"
        "print(sys.stdout.encoding, sys.stderr.encoding, file=sys.stderr)\n"
        "raise SystemExit(rc)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    # Both streams were reconfigured away from the GBK default.
    assert b"utf-8 utf-8" in proc.stderr
    # The Chinese title crossed the pipe as UTF-8 bytes, not GBK bytes.
    assert "分笔数据".encode() in proc.stdout
    payload = json.loads(proc.stdout.decode("utf-8"))
    assert payload["tick"] == "tick - 分笔数据"
