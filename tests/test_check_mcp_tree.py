"""Tests for scripts/check_mcp_tree.py, the local drift check between this
checkout and the tree the qmt MCP server is started in.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_checker():
    path = REPO_ROOT / "scripts" / "check_mcp_tree.py"
    spec = importlib.util.spec_from_file_location("check_mcp_tree", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_served_directories_reads_the_directory_argument(tmp_path, capsys):
    checker = _load_checker()
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "qmt": {
                        "command": "uv",
                        "args": [
                            "run",
                            "--directory",
                            "D:/projects/qmtcli",
                            "--extra",
                            "mcp",
                            "qmtcli",
                            "mcp",
                        ],
                    },
                    "other": {"command": "node", "args": ["server.js"]},
                }
            }
        ),
        encoding="utf-8",
    )

    directories = checker.served_directories(config)

    assert directories == [Path("D:/projects/qmtcli")]
    assert "qmt" in capsys.readouterr().out


def test_served_directories_ignores_servers_without_a_directory(tmp_path):
    checker = _load_checker()
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"qmt": {"command": "uv", "args": ["run", "qmtcli", "mcp"]}}}),
        encoding="utf-8",
    )

    assert checker.served_directories(config) == []


def test_capability_names_reports_the_exposed_commands(tmp_path):
    checker = _load_checker()
    source = tmp_path / "src" / "qmtcli"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text("", encoding="utf-8")
    (source / "__main__.py").write_text(
        "import json;"
        "print(json.dumps({'ok': True, 'data': {'commands': ["
        "{'name': 'status'}, {'name': 'buy'}]}}))",
        encoding="utf-8",
    )

    assert checker.capability_names(tmp_path) == {"buy", "status"}


def test_order_commands_are_the_guarded_set():
    checker = _load_checker()

    assert checker.ORDER_COMMANDS == {"buy", "sell", "cancel"}


def test_main_fails_when_the_served_surface_differs(tmp_path, monkeypatch, capsys):
    checker = _load_checker()
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"qmt": {"command": "uv", "args": ["run", "qmtcli", "mcp"]}}}),
        encoding="utf-8",
    )
    served = tmp_path / "served"
    served.mkdir()
    monkeypatch.setattr(checker, "served_directories", lambda path: [served])
    monkeypatch.setattr(
        checker,
        "capability_names",
        lambda tree: {"status", "buy"} if tree == served else {"status"},
    )
    monkeypatch.setattr(checker, "git_head", lambda tree: "abc1234")
    monkeypatch.setattr("sys.argv", ["check_mcp_tree.py", str(config)])

    assert checker.main() == 1
    assert "FAIL" in capsys.readouterr().out


def test_main_passes_when_the_served_surface_matches(tmp_path, monkeypatch, capsys):
    checker = _load_checker()
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"qmt": {"command": "uv", "args": ["run", "qmtcli", "mcp"]}}}),
        encoding="utf-8",
    )
    served = tmp_path / "served"
    served.mkdir()
    monkeypatch.setattr(checker, "served_directories", lambda path: [served])
    monkeypatch.setattr(checker, "capability_names", lambda tree: {"status", "buy"})
    monkeypatch.setattr(checker, "git_head", lambda tree: "abc1234")
    monkeypatch.setattr(checker, "same_tree", lambda first, second: True)
    monkeypatch.setattr("sys.argv", ["check_mcp_tree.py", str(config)])

    assert checker.main() == 0
    assert "FAIL" not in capsys.readouterr().out


def test_main_fails_when_the_binding_serves_another_checkout(tmp_path, monkeypatch, capsys):
    checker = _load_checker()
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps({"mcpServers": {"qmt": {"command": "uv", "args": ["run", "qmtcli", "mcp"]}}}),
        encoding="utf-8",
    )
    served = tmp_path / "served"
    served.mkdir()
    monkeypatch.setattr(checker, "served_directories", lambda path: [served])
    monkeypatch.setattr(checker, "capability_names", lambda tree: {"status", "buy"})
    monkeypatch.setattr(checker, "git_head", lambda tree: "abc1234")
    monkeypatch.setattr("sys.argv", ["check_mcp_tree.py", str(config)])

    assert checker.main() == 1
    assert "not this checkout" in capsys.readouterr().out
