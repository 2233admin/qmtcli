"""Compare the bridge copies the QMT client loads against this checkout.

Editing ``bridge/daqmt_server.py`` changes nothing the client runs: QMT loads
``<qmt_root>/python/大QMT.py``, and the strategy refuses to start unless every
file in ``resource_dir`` matches the digest pinned in ``connection.json``
(``bridge/README.md``). ``pytest`` is green either way, so a stale copy is
indistinguishable from a working change: the tests import this checkout, the
client does not.

This check reports the three copy states ``qmtcli bootstrap`` computes
(``bridge_source``, ``strategy_file``, ``bridge_assets``) and exits 1 when one
of them shows the running bridge is not this code.

Run with: ``python scripts/check_bridge_copies.py [qmt_root]``
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COPY_STEPS = ("bridge_source", "strategy_file", "bridge_assets")


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from qmtcli import bootstrap

    qmt_root = sys.argv[1] if len(sys.argv) > 1 else None
    result = bootstrap.run(
        qmt_root=qmt_root,
        account="unknown",
        port=9001,
        bridge_src=str(REPO_ROOT / "bridge" / "daqmt_server.py"),
    )
    steps = {step["name"]: step for step in result["steps"]}

    print(f"checkout {REPO_ROOT}")
    failed = False
    for name in COPY_STEPS:
        step = steps.get(name)
        if step is None:
            print(f"  skip    {name}: not reported")
            continue
        if name == "strategy_file" and qmt_root is None:
            print(f"  skip    {name}: pass the QMT install dir to check the strategy copy")
            continue
        print(f"  {'ok     ' if step['ok'] else 'FAIL   '} {name}: {step['detail']}")
        failed = failed or not step["ok"]

    if failed:
        print(
            "The bridge the client loads is not this checkout's code. Copy "
            "bridge/daqmt_server.py to <qmt_root>/python/大QMT.py, deploy the pinned assets, "
            "then restart the strategy in the client."
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
