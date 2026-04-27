"""FastMCP server exposing the knowledge base as MCP tools.

Run locally from the project root:

    python -m backend.expose_mcp

Then wire the stdio command into any MCP client (Claude Desktop, Cursor, etc.).
"""

from fastmcp import FastMCP

from backend.read.retrieval import hybrid_search
from backend.read.claude_answer import answer

mcp = FastMCP("stanford-eng-kb")


@mcp.tool()
def search(query: str, k: int = 5, org_id: str | None = None, sub_id: str | None = None) -> list[dict]:
    """Hybrid (vector + keyword) search over the knowledge base.

    Pass org_id (and optionally sub_id) to scope to one tenant. Omitting org_id
    searches across all tenants — admin/debug only.
    """
    return hybrid_search(query, k=k, org_id=org_id, sub_id=sub_id)


@mcp.tool()
def ask(query: str, k: int = 5, org_id: str | None = None, sub_id: str | None = None) -> dict:
    """Answer a natural-language question grounded in the KB, with inline [n] citations.

    Pass org_id (and optionally sub_id) to scope retrieval to one tenant.
    """
    return answer(query, k=k, org_id=org_id, sub_id=sub_id)


if __name__ == "__main__":
    mcp.run()
