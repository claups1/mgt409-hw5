"""The team's only door to shop data: the campus-customs MCP server.

One MCPToolset launches mcp_server/mcp_server.py over stdio (with the server's
own .venv Python). Each agent gets a filtered view of that same toolset, so it
sees only the tools for its job. There is no other shop-data code in the
backend: no SQL and no direct database access.
"""

from __future__ import annotations

from fastmcp import Client
from fastmcp.client.transports import StdioTransport
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.toolsets import FilteredToolset

from config import MCP_PYTHON, MCP_SERVER_DIR, MCP_SERVER_SCRIPT

# Which MCP tools each agent may call. Anything not listed is hidden from that agent.
AGENT_MCP_TOOLS: dict[str, set[str]] = {
    "boss": {
        "list_open_tickets", "get_ticket", "get_shop_policy",
        "review_customer_order", "review_rent_notice", "review_bulk_order",
    },
    "inventory": {
        "get_ticket", "get_shop_policy", "check_inventory", "get_pricing", "list_vendors", "propose_restock",
    },
    "accounting": {
        "get_ticket", "get_shop_policy", "get_cash_position", "get_invoice", "get_lease",
        "list_payments", "get_pricing", "propose_payment", "propose_discount",
    },
    "facilities": {
        "get_ticket", "get_shop_policy", "get_lease", "list_payments",
    },
    "customer_service": {
        "get_ticket", "get_shop_policy", "check_inventory", "propose_customer_reply",
    },
}


def build_mcp_toolset() -> MCPToolset:
    transport = StdioTransport(
        command=str(MCP_PYTHON),
        args=[str(MCP_SERVER_SCRIPT)],
        cwd=str(MCP_SERVER_DIR),
    )
    return MCPToolset(Client(transport))


def toolset_for(agent: str, mcp: MCPToolset) -> FilteredToolset:
    allowed = AGENT_MCP_TOOLS[agent]
    return mcp.filtered(lambda _ctx, tool_def: tool_def.name in allowed)


async def check_server_tools(mcp: MCPToolset) -> list[str]:
    """Fail fast if an agent is assigned a tool the server doesn't have."""
    names = sorted(t.name for t in await mcp.client.list_tools())
    missing = set().union(*AGENT_MCP_TOOLS.values()) - set(names)
    if missing:
        raise RuntimeError(f"MCP server is missing tools assigned to agents: {sorted(missing)}")
    return names
