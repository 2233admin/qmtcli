"""From a broker QMT install to a verified bridge, on a fresh host.

Every step here is a fact with a digest or a path attached, so a new machine can
be brought up by one command plus the two things no program may do for the
operator (broker installer, GUI login):

    uv run qmtcli bootstrap --account 12345678          # report only
    uv run qmtcli bootstrap --account 12345678 --apply  # copy the bridge in

What it deliberately does not do: download QMT, download the fixed release,
write the bridge secret (``qmtcli-rs setup`` owns that file and its DACL), or
start a strategy inside the client.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.request
from pathlib import Path

# The bridge entry point as it is shipped in this repository (bridge/README.md).
BRIDGE_SHA256 = "c9e0513315898306e3710805ac40dc664e9cf95b183e9b17c5e66b2d547924a6"
STRATEGY_FILENAME = "大QMT.py"

# The release artifact k-atana's gateway accepts by digest (qmtcli_transport.FIXED_SHA256).
FIXED_RELEASE_SHA256 = "7749aaece5b71f697cb0e6ebc5bf91d655d5353b94cfc7f66f5b64eb323e16d1"

MANUAL_STEPS = [
    "在客户端里登录资金账号 (图形界面, 程序不能代做)",
    "把 strategy 文件加载为策略, 勾选『自动运行』: {root}/python/" + STRATEGY_FILENAME,
    "登录后重跑 qmtcli bootstrap, 所有 step 全绿才算部署完成",
]


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _step(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def release_path(host_dir: Path) -> Path:
    return host_dir / "releases" / FIXED_RELEASE_SHA256[:8] / "qmtcli-rs.exe"


def _bridge_source(explicit: str | None) -> Path | None:
    if explicit:
        candidate = Path(explicit)
        return candidate if candidate.is_file() else None
    here = Path(__file__).resolve()
    for parent in here.parents:  # repo checkout: <repo>/src/qmtcli/bootstrap.py -> <repo>/bridge
        candidate = parent / "bridge" / "daqmt_server.py"
        if candidate.is_file():
            return candidate
    return None


def _probe(base_url: str | None, secret: str) -> dict | None:
    if not base_url:
        return None

    def get(path: str):
        request = urllib.request.Request(f"{base_url}{path}", headers={"X-Bridge-Secret": secret})
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - loopback
            return json.loads(response.read())

    try:
        health = get("/api/health")
        asset = get("/api/account/asset")
    except Exception as exc:  # noqa: BLE001 - an unreachable bridge is a reported step
        return {"reachable": False, "detail": f"{type(exc).__name__}: {exc}"}
    return {
        "reachable": bool(health.get("bridge_running")),
        "bridge_running": health.get("bridge_running"),
        "trading_enabled": health.get("trading_enabled"),
        "cash": asset.get("cash"),
    }


def run(
    *,
    qmt_root: str | None,
    account: str,
    port: int,
    host_dir: str | None = None,
    bridge_src: str | None = None,
    apply: bool = False,
    base_url: str | None = None,
    secret: str = "",
) -> dict:
    host = (Path(host_dir) if host_dir
            else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "QmtCli")
    steps: list[dict] = []
    root = Path(qmt_root) if qmt_root else None
    steps.append(_step("qmt_root", bool(root and (root / "python").is_dir()),
                       str(root) if root else "pass --qmt-root (client install dir)"))

    source = _bridge_source(bridge_src)
    source_ok = source is not None and _sha256(source) == BRIDGE_SHA256
    steps.append(_step("bridge_source", source_ok,
                       f"{source} sha256={'match' if source_ok else 'missing or unexpected'}"))

    if root is not None and (root / "python").is_dir():
        target = root / "python" / STRATEGY_FILENAME
        if target.is_file():
            same = _sha256(target) == BRIDGE_SHA256
            steps.append(_step("strategy_file", same, f"{target} {'already current' if same else 'DIFFERS'}"))
        elif apply and source_ok:
            shutil.copyfile(source, target)
            steps.append(_step("strategy_file", _sha256(target) == BRIDGE_SHA256, f"copied to {target}"))
        else:
            steps.append(_step("strategy_file", False, f"{target} absent (rerun with --apply to copy)"))
    elif root is None:
        steps.append(_step("strategy_file", False, "unknown: no qmt_root"))

    exe = release_path(host)
    exe_ok = exe.is_file() and _sha256(exe) == FIXED_RELEASE_SHA256
    steps.append(_step("fixed_release", exe_ok,
                       f"{exe} expected sha256 {FIXED_RELEASE_SHA256}"
                       if not exe_ok else str(exe)))

    connection = host / "daqmt" / "connection.json"
    steps.append(_step("connection", connection.is_file(),
                       str(connection) if connection.is_file()
                       else f"run: {exe} setup --account {account} --port {port}"))

    probe = _probe(base_url, secret)
    if probe is not None:
        steps.append(_step("bridge_live", bool(probe.get("reachable")), str(probe)))

    return {
        "ok": all(step["ok"] for step in steps),
        "host_dir": str(host),
        "account": account,
        "applied": apply,
        "steps": steps,
        "manual_steps": [step.format(root=root or "<qmt-root>") for step in MANUAL_STEPS],
    }
