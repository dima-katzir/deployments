import os
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.middleware import AuthMiddleware

from gateway_common import (
    OAUTH_META,
    READ_ONLY_ANNOTATIONS,
    build_auth,
    call_backend,
    chatgpt_fetch_result,
    chatgpt_search_result,
    require_owner,
    safe_identifier,
)


PROJECT = "life-os"
BACKEND_URL = os.environ.get("BASIC_MEMORY_BACKEND_URL", "http://life-backend:8000/mcp")
ALLOWED_BACKEND_TOOLS = frozenset({"search_notes", "read_note"})

auth = build_auth()
mcp = FastMCP(
    "Life OS Read-Only Memory",
    auth=auth,
    middleware=[AuthMiddleware(auth=require_owner)],
    instructions=(
        "Read-only retrieval for the Life OS knowledge base. "
        "Use search to locate relevant material and fetch to retrieve the full note."
    ),
)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def search(query: str) -> list[dict[str, str]]:
    """Hybrid semantic and keyword search of the Life OS knowledge base."""
    if not query.strip():
        raise ValueError("query cannot be empty")
    payload = await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "search_notes",
        {
            "project": PROJECT,
            "query": query,
            "page": 1,
            "page_size": 10,
            "search_type": "hybrid",
            "search_all_projects": False,
            "output_format": "json",
        },
    )
    return chatgpt_search_result(payload, query)


@mcp.tool(annotations=READ_ONLY_ANNOTATIONS, meta=OAUTH_META, output_schema=None)
async def fetch(id: str) -> list[dict[str, str]]:
    """Fetch the complete Life OS note identified by a search result."""
    identifier = safe_identifier(PROJECT, id)
    payload: Any = await call_backend(
        BACKEND_URL,
        ALLOWED_BACKEND_TOOLS,
        "read_note",
        {
            "project": PROJECT,
            "identifier": identifier,
            "include_frontmatter": True,
            "output_format": "text",
        },
    )
    return chatgpt_fetch_result(payload, identifier)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001)
