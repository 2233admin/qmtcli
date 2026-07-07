"""stdio MCP server exposing qmtcli commands as MCP tools.

Design principle: capabilities-driven, single source of truth. Every tool is generated from
``AGENT_CAPABILITIES`` (see ``qmtcli.cli``) and every tool call is dispatched through the existing
``_handle_rpc_request`` rpc machinery -- there is no second command registry to keep in sync with
the CLI/rpc/server surface.

Import of the `mcp` SDK is confined to this module; ``qmtcli.cli`` only imports ``run_mcp_server``
lazily from here when the ``mcp`` subcommand actually runs, so the rest of qmtcli (and its test
suite) works without the optional ``mcp`` extra installed.
"""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from qmtcli.cli import AGENT_CAPABILITIES, _handle_rpc_request, _json_default

# --- capability -> tool translation -------------------------------------------------------------

# Danger levels that must never be reachable over MCP: qmtcli-over-MCP stays a read + guarded
# escape-hatch surface for agents; order placement/cancellation remain CLI/rpc/server only.
_EXCLUDED_DANGERS = {"places_order", "cancels_order"}

# trade_call is an unguarded escape hatch onto the *entire* XtQuantTrader surface (which includes
# order placement/cancellation under other method names), so it is excluded by name even though
# its own "danger" is "escape_hatch" rather than places_order/cancels_order. data_call is the
# read-only xtdata equivalent and stays included. "rpc"/"server"/"mcp" are defensive: none of them
# are AGENT_CAPABILITIES commands today except "mcp" itself (added below), but excluding all three
# by name means adding a future meta-command with one of these names can never accidentally turn
# into a self-referential or transport-only MCP tool.
_EXCLUDED_NAMES = {"trade_call", "rpc", "server", "mcp"}

# Shared parameters most trade-query/account tools need; documented once here instead of repeating
# path/account/account_type in every AGENT_CAPABILITIES entry's own "inputs".
_SHARED_PROPERTIES: dict[str, dict[str, Any]] = {
    "path": {"type": "string", "description": "QMT install root or userdata_mini path"},
    "account": {"type": "string", "description": "QMT account id"},
    "account_type": {"type": "string", "description": "QMT account type", "default": "STOCK"},
}


def _tool_name(command_name: str) -> str:
    return "qmt_" + command_name.replace("-", "_")


def _dispatch_command(command: dict[str, Any]) -> str:
    """The string that should appear as request["command"] for _handle_rpc_request."""
    return command.get("rpc_command", command["name"])


def _is_excluded(command: dict[str, Any]) -> bool:
    if command.get("danger") in _EXCLUDED_DANGERS:
        return True
    if command["name"] in _EXCLUDED_NAMES:
        return True
    # Anything restricted to a transport list that excludes "rpc" cannot be reached through
    # _handle_rpc_request, which is exactly the machinery MCP dispatch always goes through. This
    # covers the subscribe/subscribe_whole/unsubscribe trio (transports: ["server"], streaming,
    # only meaningful while a server-mode process stays alive) *and* watch (transports: ["cli"], a
    # blocking xtdata.run() loop that is deliberately excluded from DATA_COMMAND_NAMES and unknown
    # to _handle_rpc_data) with one general rule instead of hard-coding each case.
    transports = command.get("transports")
    if transports is not None and "rpc" not in transports:
        return True
    return False


def _included_commands() -> list[dict[str, Any]]:
    return [command for command in AGENT_CAPABILITIES["commands"] if not _is_excluded(command)]


def _input_schema(command: dict[str, Any]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for param, description in command.get("inputs", {}).items():
        # JSON Schema allows "type" to be an array of allowed types; every AGENT_CAPABILITIES
        # input is prose-typed rather than schema-typed, so this stays permissive rather than
        # guessing a single JSON type from the free-text description.
        properties[param] = {
            "type": ["string", "number", "boolean", "array", "object"],
            "description": str(description),
        }
    for param, schema in _SHARED_PROPERTIES.items():
        # setdefault: a command that documents its own path/account/account_type (for example
        # doctor) keeps its own description instead of being overwritten by the shared one.
        properties.setdefault(param, dict(schema))
    return {"type": "object", "properties": properties, "additionalProperties": True}


def build_tool_specs() -> list[dict[str, Any]]:
    """Generate MCP tool specs from AGENT_CAPABILITIES -- the single source of truth.

    Excludes order placement/cancellation (danger places_order/cancels_order), trade_call (an
    unguarded escape hatch onto the full XtQuantTrader surface), and anything not reachable
    through the rpc transport (the subscribe trio, server-only; watch, CLI-only). Everything else
    -- status, doctor, data_call, fields, download, every named data command, and every trade
    query including asset/positions/orders/trades -- is included.
    """
    return [
        {
            "name": _tool_name(command["name"]),
            "description": command["description"],
            "inputSchema": _input_schema(command),
        }
        for command in _included_commands()
    ]


def _tool_command_map() -> dict[str, str]:
    """tool name -> the command string _handle_rpc_request should dispatch on."""
    return {_tool_name(command["name"]): _dispatch_command(command) for command in _included_commands()}


# --- dispatch ------------------------------------------------------------------------------------


async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=spec["name"], description=spec["description"], inputSchema=spec["inputSchema"])
        for spec in build_tool_specs()
    ]


async def call_tool(name: str, arguments: dict[str, Any]) -> list[types.TextContent]:
    """Dispatch one MCP tool call through _handle_rpc_request, the shared rpc/server dispatch.

    A plain module-level function (not a closure inside build_server()) so tests can call it
    directly -- unit level, no stdio session needed -- exactly like any other qmtcli dispatch
    helper.
    """
    command = _tool_command_map().get(name)
    if command is None:
        response: dict[str, Any] = {"ok": False, "error": f"unknown tool: {name}"}
    else:
        # Merge arguments *under* the resolved command, not {"command": command, **arguments}:
        # if a caller's arguments happened to include a "command" key, spreading arguments last
        # would let it silently override the dispatch target and reach an excluded command (buy,
        # sell, cancel, trade_call, subscribe, ...) through an innocuous-looking tool. Building the
        # request from arguments first and setting "command" last keeps the resolved command
        # authoritative no matter what the caller sends.
        request: dict[str, Any] = dict(arguments)
        request["command"] = command
        response = _handle_rpc_request(request)
    text = json.dumps(response, ensure_ascii=False, default=_json_default)
    return [types.TextContent(type="text", text=text)]


# --- server wiring -------------------------------------------------------------------------------


def _qmtcli_version() -> str:
    try:
        return _pkg_version("qmtcli")
    except PackageNotFoundError:  # pragma: no cover - only when running from an uninstalled tree
        return "0.0.0"


def build_server() -> Server:
    """Build the low-level mcp.server.Server, wired to AGENT_CAPABILITIES/_handle_rpc_request."""
    server = Server(name="qmtcli", version=_qmtcli_version())
    server.list_tools()(list_tools)
    server.call_tool()(call_tool)
    return server


async def _serve() -> None:
    server = build_server()
    # MCP stdio owns stdout for the JSONRPC wire protocol; nothing in this module (or in
    # _handle_rpc_request/_json_default, both reused as-is from qmtcli.cli) prints to stdout.
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def run_mcp_server() -> int:
    """Entry point for `qmtcli mcp`: serve stdio MCP until the client closes stdin (Ctrl+C exits
    cleanly with code 0, matching the existing `watch` command's KeyboardInterrupt handling).
    """
    try:
        anyio.run(_serve)
    except KeyboardInterrupt:
        pass
    return 0
