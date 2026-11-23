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
import subprocess
import urllib.request
from pathlib import Path

# The bridge entry point as it is shipped in this repository (bridge/README.md).
BRIDGE_SHA256 = "5dbe42af9233736bd37d75f2671588c9a27600116ea7c57b18240f404833aa0f"
STRATEGY_FILENAME = "大QMT.py"

# The release artifact k-atana's gateway accepts by digest (qmtcli_transport.FIXED_SHA256).
FIXED_RELEASE_SHA256 = "7749aaece5b71f697cb0e6ebc5bf91d655d5353b94cfc7f66f5b64eb323e16d1"

# Every file connection.json pins by sha256. The strategy refuses to start when one
# is missing or differs, so deploying only the entry point leaves a half-installed bridge.
PINNED_ASSETS = (
    "daqmt_server.py",
    "daqmt_api.py",
    "daqmt_codec.py",
    "daqmt_stream.py",
    "catalog.json",
)

# Order-safety keys an older connection file predates. The bridge defaults an absent one
# to off, so this only makes the current values visible in the report.
TRADING_DEFAULTS = {
    "dry_run": False,
    "max_order_amount": 500000,
    "passorder_form": "full",
}

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


def _ensure_trading_config(connection: Path) -> list[str]:
    """Add the order-safety keys an older connection file predates."""
    try:
        config = json.loads(connection.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    missing = [key for key in TRADING_DEFAULTS if key not in config]
    if not missing:
        return []
    config.update({key: TRADING_DEFAULTS[key] for key in missing})
    connection.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return ["added " + ", ".join(missing)]


def _pinned_assets(connection: Path) -> dict | None:
    """The assets map connection.json pins, or None when it cannot be read."""
    try:
        config = json.loads(connection.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    assets = config.get("assets")
    return assets if isinstance(assets, dict) else None


def _asset_states(source_dir: Path, resource: Path, pinned: dict | None = None) -> dict[str, dict]:
    """Per asset: in the repo, deployed byte-identical, and digest recorded in the config.

    A wrong digest matters as much as a wrong file: the strategy refuses to start on a
    mismatch, so the file check alone would report green on a config that cannot boot.
    """
    states: dict[str, dict] = {}
    for name in PINNED_ASSETS:
        src = source_dir / name
        if not src.is_file():
            states[name] = _step(name, False, f"missing in {source_dir}")
            continue
        dst = resource / name
        if not dst.is_file():
            states[name] = _step(name, False, "not deployed")
            continue
        digest = _sha256(dst)
        if digest != _sha256(src):
            states[name] = _step(name, False, f"DIFFERS from {src}")
        elif pinned is not None and pinned.get(name) != digest:
            states[name] = _step(name, False, "digest not pinned in connection.json")
        else:
            states[name] = _step(name, True, "current")
    return states


def _asset_step(states: dict[str, dict]) -> dict:
    """Collapse the per-asset states into one reported step."""
    stale = [name for name, state in states.items() if not state["ok"]]
    detail = (
        "all current"
        if not stale
        else "; ".join(f"{name}: {states[name]['detail']}" for name in stale)
    )
    return _step("bridge_assets", not stale, detail)


def _retarget_assets(connection: Path, resource: Path) -> dict:
    """Point connection.json.assets at the bytes now sitting in resource_dir.

    Only the assets map is touched. The secret, account and flags belong to
    qmtcli-rs setup, and the strategy refuses to start on a digest mismatch, so this
    must run after the copies and before the next strategy start.
    """
    try:
        config = json.loads(connection.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _step("assets_digests", False, f"cannot read {connection}")
    assets = config.get("assets")
    if not isinstance(assets, dict):
        return _step("assets_digests", False, "connection.json has no assets map")
    changed = []
    for name in PINNED_ASSETS:
        asset = resource / name
        if not asset.is_file():
            return _step("assets_digests", False, f"missing {asset}")
        digest = _sha256(asset)
        if assets.get(name) != digest:
            assets[name] = digest
            changed.append(name)
    if changed:
        connection.write_text(
            json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    detail = "updated " + ", ".join(changed) if changed else "digests already match"
    return _step("assets_digests", True, detail)


def _run_setup(exe: Path, account: str, port: int) -> dict:
    """Create connection.json through the pinned binary that owns the secret."""
    try:
        result = subprocess.run(
            [str(exe), "setup", "--account", account, "--port", str(port)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return _step("setup", False, f"{type(exc).__name__}: {exc}")
    output = (result.stdout + result.stderr).strip()[:200]
    return _step("setup", result.returncode == 0, f"exit {result.returncode} {output}".strip())


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


def _connection_target(connection: Path) -> tuple[str, str] | None:
    """Endpoint and secret from connection.json, so the probe needs no flags."""
    try:
        config = json.loads(connection.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(config, dict):
        return None
    endpoint = str(config.get("endpoint") or "").rstrip("/")
    if not endpoint:
        return None
    return endpoint, str(config.get("secret") or "")


def _probe(base_url: str | None, secret: str, target: tuple[str, str] | None = None) -> dict | None:
    """Health of a running bridge, from --base-url or from connection.json."""
    endpoint = base_url.rstrip("/") if base_url else (target[0] if target else "")
    if not endpoint:
        return None
    key = secret or (target[1] if target else "")

    def get(path: str):
        request = urllib.request.Request(f"{endpoint}{path}", headers={"X-Bridge-Secret": key})
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
        "bridge_sha256": health.get("bridge_sha256"),
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
    host = (
        Path(host_dir)
        if host_dir
        else Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "QmtCli"
    )
    steps: list[dict] = []
    root = Path(qmt_root) if qmt_root else None
    steps.append(
        _step(
            "qmt_root",
            bool(root and (root / "python").is_dir()),
            str(root) if root else "pass --qmt-root (client install dir)",
        )
    )

    source = _bridge_source(bridge_src)
    source_ok = source is not None and _sha256(source) == BRIDGE_SHA256
    steps.append(
        _step(
            "bridge_source",
            source_ok,
            f"{source} sha256={'match' if source_ok else 'missing or unexpected'}",
        )
    )

    if root is not None and (root / "python").is_dir():
        target = root / "python" / STRATEGY_FILENAME
        if target.is_file() and _sha256(target) == BRIDGE_SHA256:
            steps.append(_step("strategy_file", True, f"{target} already current"))
        elif apply and source_ok:
            existed = target.is_file()
            shutil.copyfile(source, target)
            steps.append(
                _step(
                    "strategy_file",
                    _sha256(target) == BRIDGE_SHA256,
                    f"{target} {'overwritten' if existed else 'copied'}",
                )
            )
        elif target.is_file():
            steps.append(
                _step("strategy_file", False, f"{target} DIFFERS (rerun with --apply to overwrite)")
            )
        else:
            steps.append(
                _step("strategy_file", False, f"{target} absent (rerun with --apply to copy)")
            )
    elif root is None:
        steps.append(_step("strategy_file", False, "unknown: no qmt_root"))

    exe = release_path(host)
    exe_ok = exe.is_file() and _sha256(exe) == FIXED_RELEASE_SHA256
    steps.append(
        _step(
            "fixed_release",
            exe_ok,
            f"{exe} expected sha256 {FIXED_RELEASE_SHA256}" if not exe_ok else str(exe),
        )
    )

    resource = host / "daqmt"
    connection = resource / "connection.json"
    if not connection.is_file() and apply and exe_ok:
        steps.append(_run_setup(exe, account, port))
    steps.append(
        _step(
            "connection",
            connection.is_file(),
            str(connection)
            if connection.is_file()
            else f"run: {exe} setup --account {account} --port {port}",
        )
    )
    if connection.is_file() and apply:
        added = _ensure_trading_config(connection)
        steps.append(
            _step(
                "trading_config",
                True,
                ", ".join(added) or "trading keys present: " + ", ".join(TRADING_DEFAULTS),
            )
        )
    if source is not None:
        states = _asset_states(source.parent, resource, _pinned_assets(connection))
        stale = [name for name, state in states.items() if not state["ok"]]
        if apply and stale and connection.is_file():
            resource.mkdir(parents=True, exist_ok=True)
            for name in PINNED_ASSETS:
                shutil.copyfile(source.parent / name, resource / name)
            steps.append(_retarget_assets(connection, resource))
            states = _asset_states(source.parent, resource, _pinned_assets(connection))
        steps.append(_asset_step(states))

    probe = _probe(base_url, secret, _connection_target(connection))
    if probe is not None:
        running = probe.get("bridge_sha256")
        fresh = running is not None and running == BRIDGE_SHA256
        detail = str(probe)
        if probe.get("reachable") and not fresh:
            detail = "running %s, on disk %s: restart the strategy in the client" % (
                running[:12] if running else "an unknown build",
                BRIDGE_SHA256[:12],
            )
        steps.append(_step("bridge_live", bool(probe.get("reachable")) and fresh, detail))

    return {
        "ok": all(step["ok"] for step in steps),
        "host_dir": str(host),
        "account": account,
        "applied": apply,
        "steps": steps,
        "manual_steps": [step.format(root=root or "<qmt-root>") for step in MANUAL_STEPS],
    }
