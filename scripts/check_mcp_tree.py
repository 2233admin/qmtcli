"""Compare the tree the qmt MCP server serves against this checkout.

The MCP server is started from ``~/.omp/agent/mcp.json`` with a ``--directory``
argument naming the tree it serves. When that is a different checkout of the
same project, every ``qmt_*`` tool answers from code the agent is not editing:
a different command surface, a different order policy, a different bug fix.

This check prints both trees, their git HEADs, and the capability names each
exposes. It exits 1 when the MCP server serves a different checkout than this
one, or when the two command surfaces differ, so a stale binding fails loudly
instead of silently answering from the wrong code.

Run with: ``python scripts/check_mcp_tree.py [path/to/mcp.json]``
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MCP_CONFIG = Path.home() / ".omp" / "agent" / "mcp.json"
ORDER_COMMANDS = {"buy", "sell", "cancel"}


def served_directories(config_path: Path) -> list[Path]:
    """Return the --directory each qmtcli MCP server is started in."""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"cannot read {config_path}: {exc}", file=sys.stderr)
        return []
    servers = config.get("mcpServers", {})
    directories: list[Path] = []
    for name, server in servers.items():
        args = [str(server.get("command", ""))] + [str(a) for a in server.get("args", [])]
        if not any("qmtcli" in arg for arg in args):
            continue
        if "--directory" not in args:
            continue
        index = args.index("--directory")
        if index + 1 < len(args):
            directories.append(Path(args[index + 1]))
        print(f"mcp server '{name}' serves {args[index + 1]}")
    return directories


def capability_names(tree: Path) -> set[str]:
    """The command names the checkout at `tree` exposes.

    The tree's own CLI answers this, so the probe reads the tree the way its
    users do rather than importing it into this process.
    """
    source = tree / "src"
    if not source.is_dir():
        return set()
    env = dict(os.environ, PYTHONPATH=str(source))
    result = subprocess.run(
        [sys.executable, "-m", "qmtcli", "capabilities"],
        cwd=tree,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"cannot probe {tree}: {result.stderr.strip()}", file=sys.stderr)
        return set()
    payload = json.loads(result.stdout)
    return {command["name"] for command in payload["data"]["commands"]}


def same_tree(first: Path, second: Path) -> bool:
    """Whether two paths name the same directory (Windows paths compare case-insensitively)."""
    try:
        left = os.path.normcase(str(first.resolve()))
        right = os.path.normcase(str(second.resolve()))
    except OSError:
        return False
    return left == right


def git_head(tree: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(tree), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else "not a git checkout"


def main() -> int:
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MCP_CONFIG
    if not config_path.exists():
        print(f"no MCP config at {config_path}; nothing to compare")
        return 0

    trees = served_directories(config_path)
    if not trees:
        print("no qmtcli MCP server with a --directory binding in this config")
        return 0

    local = capability_names(REPO_ROOT)
    local_head = git_head(REPO_ROOT)
    print(f"checkout {REPO_ROOT} @ {local_head}")

    failed = False
    for tree in trees:
        served = capability_names(tree)
        served_head = git_head(tree)
        print(f"served   {tree} @ {served_head}")
        if not same_tree(tree, REPO_ROOT):
            print(
                f"  FAIL: the MCP server serves {tree}, not this checkout ({REPO_ROOT}). "
                "Point the binding at this checkout, or move the work to the served tree."
            )
            failed = True
        extra = sorted(served - local)
        missing = sorted(local - served)
        if extra:
            print(f"  served tree exposes commands this checkout does not: {', '.join(extra)}")
        if missing:
            print(f"  this checkout exposes commands the served tree does not: {', '.join(missing)}")
        if extra or missing:
            order_note = ""
            if (ORDER_COMMANDS & (served | local)):
                order_note = (
                    " The order surface differs, so the served tree and this checkout do not agree "
                    "on whether buy/sell/cancel exist."
                )
            print(
                "  FAIL: the served tree's command surface differs from this checkout's."
                f"{order_note} Point the MCP binding at this checkout, or align the served copy."
            )
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
