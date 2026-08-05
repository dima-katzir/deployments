import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import SSETransport


LIFE_URL = os.environ.get("LIFE_BACKEND_URL", "http://life-backend:8000/mcp")
GENERAL_URL = os.environ.get("GENERAL_BACKEND_URL", "http://general-backend:8000/mcp")
LIFE_ROOT = Path(os.environ.get("LIFE_ROOT", "/app/data/life-os"))


def value(result: Any) -> Any:
    if result.structured_content is not None:
        return result.structured_content
    if result.data is not None:
        return result.data
    if len(result.content) == 1 and hasattr(result.content[0], "text"):
        text = result.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return None


def compact_results(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    return [
        {
            "title": item.get("title"),
            "permalink": item.get("permalink"),
            "score": item.get("score"),
        }
        for item in results[:5]
        if isinstance(item, dict)
    ]


def manifest() -> dict[str, str]:
    return {
        str(path.relative_to(LIFE_ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(LIFE_ROOT.glob("*.md"))
    }


async def main() -> None:
    query = "when reorganizing systems becomes avoidance, return to concrete progress"
    async with Client(SSETransport(url=LIFE_URL)) as life:
        life_tools = sorted(tool.name for tool in await life.list_tools())
        vector = value(
            await life.call_tool(
                "search_notes",
                {
                    "project": "life-os",
                    "query": query,
                    "search_type": "vector",
                    "search_all_projects": False,
                    "page_size": 5,
                    "output_format": "json",
                },
            )
        )
        hybrid = value(
            await life.call_tool(
                "search_notes",
                {
                    "project": "life-os",
                    "query": query,
                    "search_type": "hybrid",
                    "search_all_projects": False,
                    "page_size": 5,
                    "output_format": "json",
                },
            )
        )

    async with Client(SSETransport(url=GENERAL_URL)) as general:
        general_tools = sorted(tool.name for tool in await general.list_tools())

    vector_results = compact_results(vector)
    hybrid_results = compact_results(hybrid)
    if not vector_results:
        raise SystemExit("vector search returned no results")
    if not hybrid_results:
        raise SystemExit("hybrid search returned no results")

    print(
        json.dumps(
            {
                "life_backend_tools": life_tools,
                "general_backend_tools": general_tools,
                "vector_results": vector_results,
                "hybrid_results": hybrid_results,
                "life_manifest": manifest(),
            },
            indent=2,
        )
    )


asyncio.run(main())
