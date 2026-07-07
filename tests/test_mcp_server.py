"""stdio MCP server: tools generated from AGENT_CAPABILITIES, dispatched through the existing
_handle_rpc_request rpc machinery. See src/qmtcli/mcp_server.py for the design rationale (single
source of truth, no second command registry).
"""

from __future__ import annotations

import builtins
import json
import sys

import anyio

from qmtcli.cli import AGENT_CAPABILITIES, main
from qmtcli.gateway import QMTGateway
from qmtcli.mcp_server import build_server, build_tool_specs, call_tool, list_tools


def _spec_names() -> set[str]:
    return {spec["name"] for spec in build_tool_specs()}


def test_build_tool_specs_excludes_dangerous_and_unreachable_commands():
    names = _spec_names()
    for excluded in (
        "qmt_buy",
        "qmt_sell",
        "qmt_cancel",
        "qmt_trade_call",
        "qmt_subscribe",
        "qmt_subscribe_whole",
        "qmt_unsubscribe",
        "qmt_watch",  # CLI-only blocking stream; not reachable via _handle_rpc_request either
        "qmt_mcp",  # would be self-referential
    ):
        assert excluded not in names, f"{excluded} must not be exposed as an MCP tool"


def test_build_tool_specs_includes_safe_and_query_commands():
    names = _spec_names()
    for included in (
        "qmt_status",
        "qmt_doctor",
        "qmt_data_call",
        "qmt_fields",
        "qmt_download",
        "qmt_full_tick",
        "qmt_sector_stocks",
        "qmt_account_infos",
        "qmt_asset",
        "qmt_positions",
        "qmt_orders",
        "qmt_trades",
    ):
        assert included in names, f"{included} should be exposed as an MCP tool"


def test_build_tool_specs_names_all_start_with_qmt_prefix():
    specs = build_tool_specs()
    assert specs
    assert all(spec["name"].startswith("qmt_") for spec in specs)


def test_build_tool_specs_schemas_are_objects_with_additional_properties():
    for spec in build_tool_specs():
        schema = spec["inputSchema"]
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is True
        assert isinstance(schema["properties"], dict)


def test_build_tool_specs_count_matches_capabilities_minus_exclusions():
    """No magic number: independently recompute the exclusion predicate from AGENT_CAPABILITIES
    itself and check build_tool_specs() agrees, so this test tracks the capability list as it
    grows instead of hard-coding today's count."""
    excluded_dangers = {"places_order", "cancels_order"}
    excluded_names = {"trade_call", "rpc", "server", "mcp"}

    def is_excluded(command: dict) -> bool:
        if command.get("danger") in excluded_dangers:
            return True
        if command["name"] in excluded_names:
            return True
        transports = command.get("transports")
        return transports is not None and "rpc" not in transports

    expected = sum(1 for command in AGENT_CAPABILITIES["commands"] if not is_excluded(command))

    assert expected > 0
    assert len(build_tool_specs()) == expected


def test_call_tool_dispatches_qmt_calendar_through_call_data(monkeypatch):
    calls = []

    def fake_call_data(method, *args, **kwargs):
        calls.append((method, args, kwargs))
        return {"method": method}

    monkeypatch.setattr(QMTGateway, "call_data", fake_call_data)

    result = anyio.run(call_tool, "qmt_calendar", {"market": "SH"})

    assert len(result) == 1
    assert result[0].type == "text"
    payload = json.loads(result[0].text)
    assert payload["ok"] is True
    assert calls == [("get_trading_calendar", ("SH",), {"start_time": "", "end_time": ""})]


def test_call_tool_command_argument_cannot_override_dispatch_target(monkeypatch):
    """A caller-supplied "command" argument must never win over the resolved dispatch target --
    otherwise any exposed tool (even the read-only qmt_status) could be hijacked into reaching an
    excluded command such as buy/sell/cancel/trade_call/subscribe through its arguments."""
    monkeypatch.setattr(QMTGateway, "is_available", lambda path=None: True)

    result = anyio.run(
        call_tool,
        "qmt_status",
        {"command": "buy", "symbol": "600519.SH", "volume": 100, "price": 1.0},
    )

    payload = json.loads(result[0].text)
    assert payload == {"ok": True, "data": {"xtquant": True}}


def test_call_tool_unknown_tool_name_returns_error_envelope():
    result = anyio.run(call_tool, "qmt_not_a_real_tool", {})

    payload = json.loads(result[0].text)
    assert payload == {"ok": False, "error": "unknown tool: qmt_not_a_real_tool"}


def test_list_tools_matches_build_tool_specs():
    tools = anyio.run(list_tools)

    assert {tool.name for tool in tools} == _spec_names()
    for tool in tools:
        assert tool.inputSchema["type"] == "object"


def test_cli_main_mcp_without_mcp_extra_reports_clean_error(monkeypatch, capsys):
    # Force a fresh import of qmtcli.mcp_server (it may already be cached from earlier tests in
    # this file) so the blocked import below actually fires instead of hitting the module cache.
    monkeypatch.delitem(sys.modules, "qmtcli.mcp_server", raising=False)
    real_import = builtins.__import__

    def blocked_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError(f"simulated: {name!r} is not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_import)

    assert main(["mcp"]) == 1

    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": False, "error": "mcp extra is not installed; pip install 'qmtcli[mcp]'"}


def test_end_to_end_stdio_session_lists_and_calls_fields_tool():
    """Offline smoke test over a real (in-memory) MCP client/server session: qmt_fields never
    touches QMTGateway/xtdata, so this needs no QMT install and no monkeypatching."""
    from mcp.shared.memory import create_connected_server_and_client_session

    async def scenario() -> None:
        server = build_server()
        async with create_connected_server_and_client_session(server) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert "qmt_fields" in names
            assert all(name.startswith("qmt_") for name in names)

            result = await client.call_tool("qmt_fields", {"kind": "tick"})
            assert result.isError is False
            payload = json.loads(result.content[0].text)
            assert payload["ok"] is True

    anyio.run(scenario)
