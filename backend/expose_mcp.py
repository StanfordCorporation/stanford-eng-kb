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
def search(query: str, k: int = 5) -> list[dict]:
    """Hybrid (vector + keyword) search over the Obsidian vault.

    Returns the top-k chunks with source path and fused score.
    """
    return hybrid_search(query, k=k)


@mcp.tool()
def ask(query: str, k: int = 5) -> dict:
    """Answer a natural-language question using the vault as grounding.

    Returns an answer string plus the sources used, with inline [n] citations.
    """
    return answer(query, k=k)


if __name__ == "__main__":
    mcp.run()
